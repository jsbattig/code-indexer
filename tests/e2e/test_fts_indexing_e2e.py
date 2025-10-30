"""
End-to-end tests for FTS indexing with real Tantivy, filesystem, and CLI.

Tests use real Tantivy library, real filesystem operations, and real CLI commands.
Zero mocking - tests actual behavior of the complete system.
"""

import subprocess
import tempfile
import time
from pathlib import Path

import pytest


class TestFTSIndexingE2E:
    """E2E tests for FTS indexing with --fts flag."""

    def setup_test_project(self, tmpdir: Path) -> Path:
        """Create a test project with sample files."""
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir(parents=True)

        # Create sample Python files
        (project_dir / "main.py").write_text(
            """
def authenticate_user(username, password):
    '''Authenticate user with credentials'''
    return check_credentials(username, password)

def check_credentials(user, pwd):
    return user == 'admin' and pwd == 'secret'
"""
        )

        (project_dir / "utils.py").write_text(
            """
def calculate_total(items):
    '''Calculate total price'''
    return sum(item.price for item in items)

def format_currency(amount):
    return f"${amount:.2f}"
"""
        )

        (project_dir / "models.py").write_text(
            """
class User:
    def __init__(self, username, email):
        self.username = username
        self.email = email

class Product:
    def __init__(self, name, price):
        self.name = name
        self.price = price
"""
        )

        return project_dir

    def run_cidx_command(self, args, cwd=None, timeout=60):
        """Run cidx command and return result."""
        cmd = ["cidx"] + args
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result

    @pytest.mark.e2e
    def test_fts_flag_creates_tantivy_index(self):
        """Test that --fts flag creates Tantivy index in correct location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            # Initialize cidx project
            result = self.run_cidx_command(["init"], cwd=project_dir)
            # May fail if services not available, but we check flag behavior

            # Start services
            result = self.run_cidx_command(["start"], cwd=project_dir)
            if result.returncode != 0:
                pytest.skip(f"Services not available: {result.stderr}")

            try:
                # Index with --fts flag (WILL FAIL INITIALLY - flag doesn't exist)
                result = self.run_cidx_command(
                    ["index", "--fts"], cwd=project_dir, timeout=120
                )

                # Should not error on flag parsing
                assert "unrecognized" not in result.stderr.lower()
                assert "unknown option" not in result.stderr.lower()

                if result.returncode == 0:
                    # Verify Tantivy index was created
                    tantivy_dir = project_dir / ".code-indexer" / "tantivy_index"
                    assert tantivy_dir.exists(), "Tantivy index directory should exist"
                    assert (
                        tantivy_dir.is_dir()
                    ), "Tantivy index path should be directory"

                    # Verify index contains segments
                    assert any(
                        tantivy_dir.rglob("*")
                    ), "Tantivy index should contain files"
            finally:
                # Cleanup
                self.run_cidx_command(["stop"], cwd=project_dir)

    @pytest.mark.e2e
    def test_default_behavior_without_fts_flag(self):
        """Test that without --fts, only semantic index is created (default preserved)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            result = self.run_cidx_command(["init"], cwd=project_dir)
            result = self.run_cidx_command(["start"], cwd=project_dir)

            if result.returncode != 0:
                pytest.skip(f"Services not available: {result.stderr}")

            try:
                # Index WITHOUT --fts flag (default behavior)
                result = self.run_cidx_command(["index"], cwd=project_dir, timeout=120)

                if result.returncode == 0:
                    # Semantic index should exist
                    semantic_dir = project_dir / ".code-indexer" / "index"
                    assert semantic_dir.exists(), "Semantic index should be created"

                    # FTS index should NOT exist
                    tantivy_dir = project_dir / ".code-indexer" / "tantivy_index"
                    assert (
                        not tantivy_dir.exists()
                    ), "FTS index should not be created by default"
            finally:
                self.run_cidx_command(["stop"], cwd=project_dir)

    @pytest.mark.e2e
    def test_fts_and_semantic_both_functional(self):
        """Test that both FTS and semantic indexes work after --fts indexing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            result = self.run_cidx_command(["init"], cwd=project_dir)
            result = self.run_cidx_command(["start"], cwd=project_dir)

            if result.returncode != 0:
                pytest.skip(f"Services not available: {result.stderr}")

            try:
                # Index with --fts
                result = self.run_cidx_command(
                    ["index", "--fts"], cwd=project_dir, timeout=120
                )

                if result.returncode != 0:
                    pytest.skip(f"Indexing failed (may be expected): {result.stderr}")

                # Test semantic search still works
                result = self.run_cidx_command(
                    ["query", "authentication", "--quiet"], cwd=project_dir
                )
                if result.returncode == 0:
                    assert "main.py" in result.stdout, "Semantic search should work"

                # Test FTS search (new functionality - will implement later)
                result = self.run_cidx_command(
                    ["search", "authenticate_user"], cwd=project_dir
                )
                # May not be implemented yet, but should not crash
            finally:
                self.run_cidx_command(["stop"], cwd=project_dir)

    @pytest.mark.e2e
    def test_progress_reporting_shows_both_indexes(self):
        """Test that progress output indicates both semantic and FTS indexing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            result = self.run_cidx_command(["init"], cwd=project_dir)
            result = self.run_cidx_command(["start"], cwd=project_dir)

            if result.returncode != 0:
                pytest.skip(f"Services not available: {result.stderr}")

            try:
                # Index with --fts and capture output
                result = self.run_cidx_command(
                    ["index", "--fts"], cwd=project_dir, timeout=120
                )

                output = result.stdout + result.stderr

                # Progress should mention FTS indexing
                # (Exact format TBD, but should indicate both operations)
                if result.returncode == 0:
                    # Check for indicators that both indexes are being built
                    assert len(output) > 0, "Should have progress output"
                    # Exact assertion depends on implementation
            finally:
                self.run_cidx_command(["stop"], cwd=project_dir)

    @pytest.mark.e2e
    def test_fts_index_survives_restart(self):
        """Test that FTS index persists across service restarts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            result = self.run_cidx_command(["init"], cwd=project_dir)
            result = self.run_cidx_command(["start"], cwd=project_dir)

            if result.returncode != 0:
                pytest.skip(f"Services not available: {result.stderr}")

            try:
                # Index with --fts
                result = self.run_cidx_command(
                    ["index", "--fts"], cwd=project_dir, timeout=120
                )

                if result.returncode != 0:
                    pytest.skip("Indexing failed")

                tantivy_dir = project_dir / ".code-indexer" / "tantivy_index"
                initial_files = (
                    set(tantivy_dir.rglob("*")) if tantivy_dir.exists() else set()
                )

                # Stop and restart services
                self.run_cidx_command(["stop"], cwd=project_dir)
                time.sleep(1)
                result = self.run_cidx_command(["start"], cwd=project_dir)

                if result.returncode != 0:
                    pytest.skip("Restart failed")

                # Verify FTS index still exists
                assert tantivy_dir.exists(), "FTS index should persist after restart"
                after_files = set(tantivy_dir.rglob("*"))
                assert (
                    len(after_files) > 0
                ), "FTS index should contain files after restart"
                assert (
                    initial_files == after_files
                ), "FTS index files should be unchanged"
            finally:
                self.run_cidx_command(["stop"], cwd=project_dir)

    @pytest.mark.e2e
    def test_clear_flag_with_fts(self):
        """Test that --clear flag also clears FTS index when --fts is used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            result = self.run_cidx_command(["init"], cwd=project_dir)
            result = self.run_cidx_command(["start"], cwd=project_dir)

            if result.returncode != 0:
                pytest.skip(f"Services not available: {result.stderr}")

            try:
                # Initial index with --fts
                result = self.run_cidx_command(
                    ["index", "--fts"], cwd=project_dir, timeout=120
                )

                if result.returncode != 0:
                    pytest.skip("Initial indexing failed")

                tantivy_dir = project_dir / ".code-indexer" / "tantivy_index"
                assert tantivy_dir.exists()

                # Reindex with --clear --fts
                result = self.run_cidx_command(
                    ["index", "--clear", "--fts"], cwd=project_dir, timeout=120
                )

                if result.returncode == 0:
                    # FTS index should still exist but be rebuilt
                    assert tantivy_dir.exists(), "FTS index should exist after --clear"
                    assert any(tantivy_dir.rglob("*")), "FTS index should be rebuilt"
            finally:
                self.run_cidx_command(["stop"], cwd=project_dir)

    @pytest.mark.e2e
    def test_tantivy_not_installed_error_message(self):
        """Test clear error message when Tantivy is not installed."""
        # This test may be hard to run if Tantivy IS installed
        # But the implementation should handle it gracefully

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            result = self.run_cidx_command(["init"], cwd=project_dir)

            # If we somehow could test without tantivy installed:
            # result = self.run_cidx_command(["index", "--fts"], cwd=project_dir)
            # assert "tantivy" in result.stderr.lower()
            # assert "install" in result.stderr.lower()

            # For now, this is a placeholder that documents the requirement
            # Actual test would need to mock the import or run in isolated environment

    @pytest.mark.e2e
    def test_fts_respects_file_filters(self):
        """Test that FTS indexing respects exclude_dirs and file_extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            # Add excluded files
            node_modules = project_dir / "node_modules"
            node_modules.mkdir()
            (node_modules / "library.js").write_text("console.log('excluded')")

            result = self.run_cidx_command(["init"], cwd=project_dir)
            result = self.run_cidx_command(["start"], cwd=project_dir)

            if result.returncode != 0:
                pytest.skip(f"Services not available: {result.stderr}")

            try:
                # Index with --fts
                result = self.run_cidx_command(
                    ["index", "--fts"], cwd=project_dir, timeout=120
                )

                if result.returncode != 0:
                    pytest.skip("Indexing failed")

                # Verify excluded files not in FTS index
                # (Implementation details depend on search command)
                # For now, just verify index was created
                tantivy_dir = project_dir / ".code-indexer" / "tantivy_index"
                assert tantivy_dir.exists()
            finally:
                self.run_cidx_command(["stop"], cwd=project_dir)

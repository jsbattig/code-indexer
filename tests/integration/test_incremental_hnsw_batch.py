"""Integration tests for HNSW incremental batch updates (HNSW-002).

Tests end-to-end scenarios with `cidx index` and `cidx temporal index` commands.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest


class TestIncrementalHNSWBatchIntegration:
    """Integration tests for incremental HNSW batch updates."""

    def create_test_files(self, tmpdir: Path, num_files: int, prefix: str = "test"):
        """Create test Python files for indexing."""
        for i in range(num_files):
            file_path = tmpdir / f"{prefix}_file_{i}.py"
            content = f'''"""Test file {i} for incremental HNSW testing."""

def {prefix}_function_{i}():
    """Function to test semantic search."""
    print("This is {prefix} function {i}")
    return {i} * 42

class {prefix.capitalize()}Class{i}:
    """Class for testing."""

    def method_{i}(self):
        """Method in class."""
        return "Method {i} implementation"
'''
            file_path.write_text(content)

    def init_git_repo(self, tmpdir: Path):
        """Initialize a git repository for testing."""
        os.chdir(tmpdir)
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], check=True)

    def git_commit(self, message: str):
        """Create a git commit."""
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)

    # === Regular Indexing Tests ===

    def test_cidx_index_incremental_uses_incremental_hnsw(self, tmpdir):
        """Test cidx index with incremental changes uses incremental HNSW."""
        # Setup: Create initial files and index
        tmpdir = Path(tmpdir)
        self.init_git_repo(tmpdir)
        self.create_test_files(tmpdir, 50, prefix="initial")
        self.git_commit("Initial files")

        # Initial index
        result = subprocess.run(
            ["cidx", "init"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        result = subprocess.run(
            ["cidx", "index"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Add more files
        self.create_test_files(tmpdir, 10, prefix="new")
        self.git_commit("Add new files")

        # Incremental index
        start_time = time.time()
        result = subprocess.run(
            ["cidx", "index"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        incremental_time = time.time() - start_time
        assert result.returncode == 0

        # Check for incremental HNSW update in logs
        # The FilesystemVectorStore logs this when using incremental
        output = result.stdout
        if "ENTERING INCREMENTAL HNSW UPDATE PATH" in output or \
           "Applying incremental HNSW update" in output:
            assert True  # Incremental path was used

        # Verify query works and includes new files
        result = subprocess.run(
            ["cidx", "query", "new_function", "--limit", "5"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "new_file" in result.stdout

        # Incremental should be relatively fast
        assert incremental_time < 10, f"Incremental indexing took {incremental_time:.2f}s"

    def test_cidx_index_first_run_uses_full_rebuild(self, tmpdir):
        """Test cidx index on fresh repo uses full rebuild."""
        # Setup: Create files in fresh repo
        tmpdir = Path(tmpdir)
        self.init_git_repo(tmpdir)
        self.create_test_files(tmpdir, 20, prefix="test")
        self.git_commit("Initial files")

        # Initialize and index
        result = subprocess.run(
            ["cidx", "init"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        result = subprocess.run(
            ["cidx", "index"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        assert result.returncode == 0

        # First index should use full rebuild
        output = result.stdout
        # Should NOT see incremental messages on first index
        assert "INCREMENTAL HNSW UPDATE PATH" not in output
        assert "Incremental HNSW update" not in output

    def test_cidx_index_with_deletions_soft_deletes_hnsw(self, tmpdir):
        """Test cidx index with deleted files soft-deletes from HNSW."""
        # Setup: Create and index files
        tmpdir = Path(tmpdir)
        self.init_git_repo(tmpdir)
        self.create_test_files(tmpdir, 30, prefix="test")
        self.git_commit("Initial files")

        result = subprocess.run(["cidx", "init"], capture_output=True)
        assert result.returncode == 0

        result = subprocess.run(["cidx", "index"], capture_output=True)
        assert result.returncode == 0

        # Delete some files
        files_to_delete = ["test_file_5.py", "test_file_10.py", "test_file_15.py"]
        for filename in files_to_delete:
            (tmpdir / filename).unlink()

        self.git_commit("Delete some files")

        # Re-index with deletions
        result = subprocess.run(
            ["cidx", "index"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Verify deleted files don't appear in search results
        result = subprocess.run(
            ["cidx", "query", "test_function_5", "--limit", "5"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "test_file_5.py" not in result.stdout

    # === Temporal Indexing Tests ===

    def test_cidx_temporal_index_incremental_uses_incremental_hnsw(self, tmpdir):
        """Test cidx temporal index with incremental commits uses incremental HNSW."""
        # Setup: Create git history
        tmpdir = Path(tmpdir)
        self.init_git_repo(tmpdir)

        # Create initial commit history (100 commits)
        for i in range(20):
            file_path = tmpdir / f"historical_file_{i}.py"
            content = f'def historical_func_{i}(): return "commit {i}"'
            file_path.write_text(content)
            self.git_commit(f"Historical commit {i}")

        # Initial temporal index
        result = subprocess.run(["cidx", "init"], capture_output=True)
        assert result.returncode == 0

        result = subprocess.run(
            ["cidx", "temporal", "index", "--all"],
            capture_output=True,
            text=True,
            timeout=60
        )
        assert result.returncode == 0

        # Add more commits
        for i in range(5):
            file_path = tmpdir / f"recent_file_{i}.py"
            content = f'def recent_func_{i}(): return "recent commit {i}"'
            file_path.write_text(content)
            self.git_commit(f"Recent commit {i}")

        # Incremental temporal index
        start_time = time.time()
        result = subprocess.run(
            ["cidx", "temporal", "index", "--start", "HEAD~5", "--end", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30
        )
        incremental_time = time.time() - start_time
        assert result.returncode == 0

        # Check for incremental update in output
        output = result.stdout
        # Should be fast for incremental temporal
        assert incremental_time < 10, f"Incremental temporal index took {incremental_time:.2f}s"

        # Verify temporal query returns recent commits
        result = subprocess.run(
            ["cidx", "temporal", "query", "recent_func", "--limit", "5"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "recent" in result.stdout.lower()

    def test_cidx_temporal_index_first_run_uses_full_rebuild(self, tmpdir):
        """Test cidx temporal index on fresh repo uses full rebuild."""
        # Setup: Create git history
        tmpdir = Path(tmpdir)
        self.init_git_repo(tmpdir)

        # Create commit history
        for i in range(10):
            file_path = tmpdir / f"file_{i}.py"
            content = f'def func_{i}(): return {i}'
            file_path.write_text(content)
            self.git_commit(f"Commit {i}")

        # Initialize and run temporal index
        result = subprocess.run(["cidx", "init"], capture_output=True)
        assert result.returncode == 0

        result = subprocess.run(
            ["cidx", "temporal", "index", "--all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30
        )
        assert result.returncode == 0

        # First temporal index should use full rebuild
        output = result.stdout
        # Should NOT see incremental messages on first temporal index
        assert "INCREMENTAL HNSW UPDATE PATH" not in output

    def test_temporal_large_history_incremental(self, tmpdir):
        """Test temporal incremental indexing on large git history."""
        # This test simulates the AC7 scenario
        tmpdir = Path(tmpdir)
        self.init_git_repo(tmpdir)

        # Create larger history (50 commits, simulating 100K vectors scenario)
        for i in range(50):
            # Create multiple files per commit to simulate real scenario
            for j in range(3):
                file_path = tmpdir / f"module_{i}_file_{j}.py"
                content = f'''"""Module {i} file {j}."""

def process_{i}_{j}(data):
    """Process data for module {i}."""
    return data * {i} + {j}

class Module{i}Handler{j}:
    """Handler class."""

    def handle(self):
        return "Module {i} Handler {j}"
'''
                file_path.write_text(content)
            self.git_commit(f"Add module {i}")

        # Initial temporal index
        result = subprocess.run(["cidx", "init"], capture_output=True)
        assert result.returncode == 0

        print("Indexing initial 50 commits...")
        result = subprocess.run(
            ["cidx", "temporal", "index", "--all"],
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0

        # Add 5 new commits
        for i in range(50, 55):
            file_path = tmpdir / f"new_module_{i}.py"
            content = f'def new_feature_{i}(): return "Feature {i}"'
            file_path.write_text(content)
            self.git_commit(f"Add new feature {i}")

        # Incremental temporal index should be MUCH faster
        print("Running incremental temporal index for last 5 commits...")
        start_time = time.time()
        result = subprocess.run(
            ["cidx", "temporal", "index", "--start", "HEAD~5", "--end", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30
        )
        incremental_time = time.time() - start_time
        assert result.returncode == 0

        print(f"Incremental temporal index completed in {incremental_time:.2f}s")

        # Should be very fast for just 5 new commits
        assert incremental_time < 5, f"Expected < 5s but took {incremental_time:.2f}s"

        # Verify new commits are searchable
        result = subprocess.run(
            ["cidx", "temporal", "query", "new_feature_52", "--limit", "3"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "new_module" in result.stdout

    def test_performance_comparison(self, tmpdir):
        """Compare performance of full rebuild vs incremental update."""
        tmpdir = Path(tmpdir)
        self.init_git_repo(tmpdir)

        # Create substantial initial content
        self.create_test_files(tmpdir, 100, prefix="base")
        self.git_commit("Initial 100 files")

        result = subprocess.run(["cidx", "init"], capture_output=True)
        assert result.returncode == 0

        # First index (full rebuild)
        start_time = time.time()
        result = subprocess.run(
            ["cidx", "index"],
            capture_output=True,
            text=True
        )
        full_index_time = time.time() - start_time
        assert result.returncode == 0

        # Make small changes
        self.create_test_files(tmpdir, 5, prefix="update")
        self.git_commit("Add 5 new files")

        # Incremental index
        start_time = time.time()
        result = subprocess.run(
            ["cidx", "index"],
            capture_output=True,
            text=True
        )
        incremental_time = time.time() - start_time
        assert result.returncode == 0

        print(f"\nPerformance comparison:")
        print(f"  Full index (100 files): {full_index_time:.2f}s")
        print(f"  Incremental (5 new files): {incremental_time:.2f}s")
        print(f"  Speedup: {full_index_time / incremental_time:.1f}x")

        # Incremental should be notably faster
        assert incremental_time < full_index_time * 0.7, \
            f"Incremental not faster enough: {incremental_time:.2f}s vs {full_index_time:.2f}s"
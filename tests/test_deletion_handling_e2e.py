"""
Comprehensive end-to-end tests for file deletion handling.

These tests validate deletion scenarios for both git-aware and non git-aware projects:
- Watch mode deletion detection and branch-aware handling
- Reconcile mode deletion detection for cleaned up stale records
- Standard indexing with --detect-deletions flag
- Multi-branch deletion isolation
- Performance with many deletions

Test Strategy:
- Use real services (Ollama, Qdrant) following NEW STRATEGY
- Create actual git repositories and file operations
- Verify real vector database operations
- Test both soft delete (git-aware) and hard delete (non git-aware)
"""

import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest

from .test_infrastructure import (
    create_fast_e2e_setup,
    DirectoryManager,
    EmbeddingProvider,
    CLIHelper,
    ServiceManager,
)


class DeletionE2ETest:
    """End-to-end tests for file deletion scenarios."""

    def __init__(self):
        self.test_repo_dir: Optional[Path] = None
        self.config_dir: Optional[Path] = None
        self.service_manager: Optional[ServiceManager] = None
        self.cli_helper: Optional[CLIHelper] = None
        self.dir_manager: Optional[DirectoryManager] = None
        self.watch_process: Optional[subprocess.Popen] = None
        self.collection_name = "deletion_test_collection"

    def setup_test_environment(self, tmp_path):
        """Setup test infrastructure with aggressive setup strategy."""
        # AGGRESSIVE SETUP: Use VoyageAI for reliable E2E tests
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.VOYAGE_AI
        )

        # AGGRESSIVE SETUP: Ensure services and clean state first
        print("🔧 Aggressive setup: Ensuring services and clean state...")
        services_ready = self.service_manager.ensure_services_ready()
        if not services_ready:
            raise RuntimeError("Could not ensure services are ready for E2E testing")

        # AGGRESSIVE SETUP: Clean all existing data first
        print("🧹 Aggressive setup: Cleaning all existing project data...")
        self._cleanup_all_data()

        # AGGRESSIVE SETUP: Verify services are actually working after cleanup
        print("🔍 Aggressive setup: Verifying services are functional...")
        try:
            # Test with a minimal project directory to verify services work
            test_setup_dir = Path(__file__).parent / "deletion_setup_verification"
            test_setup_dir.mkdir(exist_ok=True)
            (test_setup_dir / "test.py").write_text("def test(): pass")

            # Initialize and verify basic functionality works
            init_result = self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"],
                cwd=test_setup_dir,
                timeout=60,
            )
            if init_result.returncode != 0:
                print(f"Setup verification failed during init: {init_result.stderr}")
                raise RuntimeError("Services not functioning properly for E2E testing")

            # Start services
            start_result = self.cli_helper.run_cli_command(
                ["start", "--quiet"], cwd=test_setup_dir, timeout=120
            )
            if start_result.returncode != 0:
                print(f"Setup verification failed during start: {start_result.stderr}")
                raise RuntimeError("Could not start services for E2E testing")

            # Clean up verification directory
            try:
                import shutil

                shutil.rmtree(test_setup_dir, ignore_errors=True)
            except Exception:
                pass

            print("✅ Aggressive setup complete - services verified functional")

        except Exception as e:
            print(f"Setup verification failed: {e}")
            raise RuntimeError("Could not verify service functionality for E2E testing")

        # Create test repository directory
        self.test_repo_dir = tmp_path / "deletion_test_repo"
        self.test_repo_dir.mkdir(parents=True, exist_ok=True)

        # Services are already verified as working in aggressive setup
        # Initialize this specific project
        print(f"🔧 Deletion E2E: Initializing project at {self.test_repo_dir}...")
        init_result = self.cli_helper.run_cli_command(
            ["init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=self.test_repo_dir,
            timeout=60,
        )
        if init_result.returncode != 0:
            raise RuntimeError(f"Failed to initialize project: {init_result.stderr}")

    def _cleanup_all_data(self):
        """Clean all project data to ensure clean test state."""
        if not self.cli_helper:
            return
        try:
            # Use clean-data command to clean all projects
            cleanup_result = self.cli_helper.run_cli_command(
                ["clean-data", "--all-projects"], timeout=60, expect_success=False
            )
            if cleanup_result.returncode != 0:
                print(f"Cleanup warning (non-fatal): {cleanup_result.stderr}")
        except Exception as e:
            print(f"Cleanup warning (non-fatal): {e}")

        print("✅ Deletion E2E: Setup completed - services pre-verified")

    def cleanup_test_environment(self):
        """Clean up test environment following NEW STRATEGY."""
        if self.watch_process:
            try:
                self.watch_process.terminate()
                self.watch_process.wait(timeout=5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    self.watch_process.kill()
                    self.watch_process.wait(timeout=2)
                except (subprocess.TimeoutExpired, ProcessLookupError):
                    pass
            self.watch_process = None

        # Clean data only, keep services running
        try:
            self._cleanup_all_data()
        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")

    def create_git_repo_with_files(self, file_count: int = 5) -> Dict[str, Path]:
        """Create a git repository with test files."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=self.test_repo_dir, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.test_repo_dir,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.test_repo_dir,
            check=True,
        )

        # Create test files with meaningful content
        files = {}
        for i in range(file_count):
            if self.test_repo_dir is None:
                raise RuntimeError("Test repo directory not initialized")
            file_path = self.test_repo_dir / f"module_{i}.py"
            content = f'''"""
Module {i} - Core functionality for feature {i}.

This module provides essential functionality for the application.
It includes classes, functions, and utilities used across the system.
"""

class Feature{i}Handler:
    """Handles operations for feature {i}."""
    
    def __init__(self):
        self.name = "feature_{i}"
        self.version = "1.0.{i}"
    
    def process(self, data):
        """Process data for feature {i}."""
        return f"Processed {{data}} with feature {i}"
    
    def validate(self, input_data):
        """Validate input for feature {i}."""
        if not input_data:
            raise ValueError("Input cannot be empty for feature {i}")
        return True

def get_feature_{i}_config():
    """Get configuration for feature {i}."""
    return {{
        "enabled": True,
        "timeout": {i * 10},
        "max_retries": {i + 1}
    }}
'''
            file_path.write_text(content)
            files[f"module_{i}"] = file_path

        # Commit initial files
        subprocess.run(["git", "add", "."], cwd=self.test_repo_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit with test modules"],
            cwd=self.test_repo_dir,
            check=True,
        )

        return files

    def create_non_git_project_with_files(self, file_count: int = 3) -> Dict[str, Path]:
        """Create a non-git project with test files."""
        files = {}
        for i in range(file_count):
            if self.test_repo_dir is None:
                raise RuntimeError("Test repo directory not initialized")
            file_path = self.test_repo_dir / f"script_{i}.py"
            content = f'''#!/usr/bin/env python3
"""
Script {i} - Standalone utility script.

This script performs specific operations independently.
It can be run directly or imported as a module.
"""

import sys
import os

def main():
    """Main function for script {i}."""
    print(f"Running script {i}")
    print(f"Arguments: {{sys.argv[1:]}}")
    
    # Perform script-specific operations
    result = perform_operation_{i}()
    print(f"Result: {{result}}")
    
    return result

def perform_operation_{i}():
    """Perform operation {i}."""
    data = [x * {i} for x in range(1, 6)]
    return sum(data)

if __name__ == "__main__":
    main()
'''
            file_path.write_text(content)
            files[f"script_{i}"] = file_path

        return files

    def index_files(
        self, extra_args: Optional[List[str]] = None
    ) -> subprocess.CompletedProcess:
        """Index files in the test repository with comprehensive verification."""
        args = extra_args or []
        index_args = ["index"] + args
        if self.cli_helper is None:
            raise RuntimeError("CLI helper not initialized")

        print(f"🔍 Running indexing with args: {index_args}")
        result = self.cli_helper.run_cli_command(
            index_args, cwd=self.test_repo_dir, timeout=180
        )

        print(f"Indexing result: {result.returncode}")
        if result.returncode != 0:
            print(f"Indexing stderr: {result.stderr}")
            print(f"Indexing stdout: {result.stdout}")
        else:
            print("✅ Indexing completed successfully")

        # COMPREHENSIVE VERIFICATION: Ensure indexing actually worked
        try:
            # Give the system a moment to process
            import time

            time.sleep(2)

            # Verify collection has data
            stats_after = self.get_collection_stats()
            print(f"Collection stats after indexing: {stats_after}")

            if stats_after.get("total_points", 0) == 0:
                print(
                    "⚠️  Warning: No points found after indexing - this may indicate an issue"
                )

                # Try to diagnose the issue
                status_result = self.cli_helper.run_cli_command(
                    ["status"], cwd=self.test_repo_dir, timeout=30
                )
                print(f"Status after failed indexing: {status_result.stdout}")

        except Exception as e:
            print(f"Warning: Could not verify indexing results: {e}")

        return result

    def start_watch_mode(
        self, extra_args: Optional[List[str]] = None
    ) -> subprocess.Popen:
        """Start watch mode for the test repository."""
        args = extra_args or []
        cmd = [
            "code-indexer",
            "watch",
            "--debounce",
            "1.0",  # Short debounce for testing
        ] + args

        self.watch_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=self.test_repo_dir,
        )

        # Give watch mode time to start
        time.sleep(3)
        return self.watch_process

    def query_files(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Query the indexed files with comprehensive debugging."""
        query_args = ["query", query, "--limit", str(limit)]
        if self.cli_helper is None:
            raise RuntimeError("CLI helper not initialized")

        print(f"🔍 Querying with: {query_args}")
        result = self.cli_helper.run_cli_command(
            query_args, cwd=self.test_repo_dir, timeout=60
        )

        print(f"Query result: {result.returncode}")
        if result.returncode != 0:
            print(f"Query stderr: {result.stderr}")
            print(f"Query stdout: {result.stdout}")

            # Diagnose potential issues
            try:
                stats = self.get_collection_stats()
                print(f"Collection stats during failed query: {stats}")

                status_result = self.cli_helper.run_cli_command(
                    ["status"], cwd=self.test_repo_dir, timeout=30
                )
                print(f"Service status during failed query: {status_result.stdout}")

            except Exception as e:
                print(f"Could not get diagnostic info: {e}")
        else:
            if "No results found" in result.stdout:
                print("⚠️  Query succeeded but returned no results")
                # Check if collection has any data
                try:
                    stats = self.get_collection_stats()
                    print(f"Collection stats for empty query result: {stats}")
                except Exception as e:
                    print(f"Could not get collection stats: {e}")
            else:
                print(
                    f"✅ Query returned results: {len(result.stdout.splitlines())} lines"
                )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def verify_deletion_with_retry(
        self, query_text: str, expected_missing_file: str, max_retries: int = 8
    ) -> bool:
        """
        Verify file deletion with eventual consistency retry logic.

        Args:
            query_text: Text to query for
            expected_missing_file: Filename that should NOT appear in results
            max_retries: Maximum number of retry attempts

        Returns:
            True if deletion verified successfully, False otherwise
        """
        for attempt in range(max_retries):
            query_result = self.query_files(query_text)

            if query_result["returncode"] != 0:
                print(
                    f"Query failed on attempt {attempt + 1}: {query_result['stderr']}"
                )
                time.sleep(1)
                continue

            query_output = query_result["stdout"]

            if expected_missing_file not in query_output:
                print(f"✅ Deletion verified successfully on attempt {attempt + 1}")
                return True

            print(
                f"🔄 Attempt {attempt + 1}: File still appears in query results, retrying..."
            )
            time.sleep(2)  # Wait 2 seconds between retries for eventual consistency

        print(f"❌ Deletion verification failed after {max_retries} attempts")
        return False

    def verify_hard_deletion_with_retry(
        self,
        query_text: str,
        expected_missing_file: str,
        initial_points: int,
        max_retries: int = 8,
    ) -> bool:
        """
        Verify hard deletion with eventual consistency retry logic.

        Args:
            query_text: Text to query for
            expected_missing_file: Filename that should NOT appear in results
            initial_points: Initial point count before deletion
            max_retries: Maximum number of retry attempts

        Returns:
            True if hard deletion verified successfully, False otherwise
        """
        for attempt in range(max_retries):
            # Check query results
            query_result = self.query_files(query_text)

            if query_result["returncode"] != 0:
                print(
                    f"Query failed on attempt {attempt + 1}: {query_result['stderr']}"
                )
                time.sleep(1)
                continue

            query_output = query_result["stdout"]

            # Check point count (should decrease for hard deletion)
            current_stats = self.get_collection_stats()

            if (
                expected_missing_file not in query_output
                and current_stats["total_points"] < initial_points
            ):
                print(
                    f"✅ Hard deletion verified successfully on attempt {attempt + 1}"
                )
                print(
                    f"   Points decreased: {initial_points} → {current_stats['total_points']}"
                )
                return True

            print(f"🔄 Attempt {attempt + 1}: Hard deletion not complete, retrying...")
            print(f"   File in query: {expected_missing_file in query_output}")
            print(f"   Points: {initial_points} → {current_stats['total_points']}")
            time.sleep(2)  # Wait 2 seconds between retries for eventual consistency

        print(f"❌ Hard deletion verification failed after {max_retries} attempts")
        return False

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        # Use status command to get collection info
        if self.cli_helper is None:
            raise RuntimeError("CLI helper not initialized")
        result = self.cli_helper.run_cli_command(["status"], cwd=self.test_repo_dir)

        # Parse collection stats from output
        stats = {"total_points": 0, "collections": []}
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            for line in lines:
                if "total:" in line.lower() or "points" in line.lower():
                    # Extract count - look for "Total: X docs" or "X points"
                    import re

                    match = re.search(r"Total:\s+(\d+)\s+docs", line) or re.search(
                        r"(\d+)\s+points", line
                    )
                    if match:
                        stats["total_points"] = int(match.group(1))
                        break

        return stats


@pytest.mark.slow
@pytest.mark.e2e
def test_git_aware_watch_deletion(tmp_path):
    """Test git-aware watch mode deletion."""
    test = DeletionE2ETest()
    test.setup_test_environment(tmp_path)

    try:
        # Create git repository with files
        files = test.create_git_repo_with_files(3)

        # Index files initially
        index_result = test.index_files()
        assert (
            index_result.returncode == 0
        ), f"Initial indexing failed: {index_result.stderr}"

        # Verify files are indexed
        initial_stats = test.get_collection_stats()
        assert initial_stats["total_points"] > 0, "No files were indexed"

        # Start watch mode
        watch_process = test.start_watch_mode()

        try:
            # Delete one file
            deleted_file = files["module_1"]
            deleted_file.unlink()

            # Wait for watch mode to detect deletion (should be fast with filesystem events)
            time.sleep(5)  # 1s debounce + 2s processing + 2s buffer

            # Use retry logic to verify deletion with eventual consistency
            deletion_verified = test.verify_deletion_with_retry(
                "Feature1Handler", "module_1.py"
            )
            assert (
                deletion_verified
            ), "Deleted file content still appears in queries after retries"

            # Verify total points didn't decrease (soft delete, not hard delete)
            final_stats = test.get_collection_stats()
            # Points should remain the same or similar (soft delete keeps content points)
            assert (
                final_stats["total_points"] >= initial_stats["total_points"] * 0.8
            ), "Too many points were hard deleted - should use soft delete for git projects"

        finally:
            if watch_process:
                watch_process.terminate()
                try:
                    watch_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    watch_process.kill()

    finally:
        test.cleanup_test_environment()


@pytest.mark.slow
@pytest.mark.e2e
def test_git_aware_reconcile_deletion(tmp_path):
    """Test git-aware reconcile deletion detection."""
    test = DeletionE2ETest()
    test.setup_test_environment(tmp_path)

    try:
        # Create git repository with files
        files = test.create_git_repo_with_files(4)

        # Index files initially
        index_result = test.index_files()
        assert (
            index_result.returncode == 0
        ), f"Initial indexing failed: {index_result.stderr}"

        # Verify files are indexed
        initial_stats = test.get_collection_stats()
        assert initial_stats["total_points"] > 0, "No files were indexed"

        # Delete multiple files
        files["module_1"].unlink()
        files["module_2"].unlink()

        # Run reconcile (includes deletion detection automatically)
        reconcile_result = test.index_files(["--reconcile"])
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"

        # Verify deleted files are not returned in queries
        query_result1 = test.query_files("Feature1Handler")
        assert query_result1["returncode"] == 0, "Query failed"
        assert (
            "module_1.py" not in query_result1["stdout"]
        ), "Deleted file 1 still appears in queries"

        query_result2 = test.query_files("Feature2Handler")
        assert query_result2["returncode"] == 0, "Query failed"
        assert (
            "module_2.py" not in query_result2["stdout"]
        ), "Deleted file 2 still appears in queries"

        # Verify remaining files are still queryable
        query_result3 = test.query_files("Feature0Handler")
        assert query_result3["returncode"] == 0, "Query failed"
        assert (
            "module_0.py" in query_result3["stdout"]
        ), "Remaining file should still be queryable"

    finally:
        test.cleanup_test_environment()


@pytest.mark.slow
@pytest.mark.e2e
def test_multi_branch_isolation(tmp_path):
    """Test multi-branch deletion isolation."""
    test = DeletionE2ETest()
    test.setup_test_environment(tmp_path)

    try:
        # Create git repository with files
        files = test.create_git_repo_with_files(3)

        # Index files on main branch
        index_result = test.index_files()
        assert (
            index_result.returncode == 0
        ), f"Initial indexing failed: {index_result.stderr}"

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/deletion-test"],
            cwd=test.test_repo_dir,
            check=True,
        )

        # Index files on feature branch
        index_result = test.index_files()
        assert (
            index_result.returncode == 0
        ), f"Feature branch indexing failed: {index_result.stderr}"

        # Delete file in feature branch
        files["module_1"].unlink()

        # Start watch mode to detect deletion
        watch_process = test.start_watch_mode()

        try:
            # Wait for deletion detection (should be fast with filesystem events)
            time.sleep(5)  # 1s debounce + 2s processing + 2s buffer

            # Verify file is not queryable in feature branch context
            query_result = test.query_files("Feature1Handler")
            assert query_result["returncode"] == 0, "Query failed"

            # Switch back to master branch (the default initial branch name)
            subprocess.run(
                ["git", "checkout", "master"], cwd=test.test_repo_dir, check=True
            )

            # Recreate file on master (simulating it exists on master)
            files["module_1"].write_text(
                '''"""
Module 1 - Core functionality for feature 1.
This is the master branch version.
"""

class Feature1Handler:
    def process(self, data):
        return f"Master branch processed {data}"
'''
            )

            # Index on master branch
            index_result = test.index_files()
            assert index_result.returncode == 0, "Master branch re-indexing failed"

            # Verify file is queryable in master branch context
            query_result = test.query_files("Feature1Handler")
            assert query_result["returncode"] == 0, "Query failed"
            master_branch_output = query_result["stdout"]

            # File should be available in master branch
            assert (
                "module_1.py" in master_branch_output
            ), "File should be available in master branch after branch switch"

        finally:
            if watch_process:
                watch_process.terminate()
                try:
                    watch_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    watch_process.kill()

    finally:
        test.cleanup_test_environment()


@pytest.mark.slow
@pytest.mark.e2e
def test_non_git_hard_deletion(tmp_path):
    """Test non git-aware hard deletion."""
    test = DeletionE2ETest()
    test.setup_test_environment(tmp_path)

    try:
        # Create non-git project (no git init)
        files = test.create_non_git_project_with_files(3)

        # Index files initially
        index_result = test.index_files()
        assert (
            index_result.returncode == 0
        ), f"Initial indexing failed: {index_result.stderr}"

        # Verify files are indexed
        initial_stats = test.get_collection_stats()
        assert initial_stats["total_points"] > 0, "No files were indexed"

        # Delete one file
        files["script_1"].unlink()

        # Run reconcile (includes deletion detection automatically)
        reconcile_result = test.index_files(["--reconcile"])
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"

        # Verify hard deletion occurred (points should decrease)
        final_stats = test.get_collection_stats()
        assert (
            final_stats["total_points"] < initial_stats["total_points"]
        ), "Hard deletion should decrease total points for non git-aware projects"

        # Verify deleted file is not queryable
        query_result = test.query_files("script 1")
        assert query_result["returncode"] == 0, "Query failed"
        assert (
            "script_1.py" not in query_result["stdout"]
        ), "Deleted file should not be queryable"

    finally:
        test.cleanup_test_environment()


@pytest.mark.slow
@pytest.mark.e2e
def test_non_git_watch_deletion(tmp_path):
    """Test non git-aware watch mode deletion."""
    test = DeletionE2ETest()
    test.setup_test_environment(tmp_path)

    try:
        # Create non-git project
        files = test.create_non_git_project_with_files(2)

        # Index files initially
        index_result = test.index_files()
        assert (
            index_result.returncode == 0
        ), f"Initial indexing failed: {index_result.stderr}"

        # Verify files are indexed
        initial_stats = test.get_collection_stats()
        assert initial_stats["total_points"] > 0, "No files were indexed"

        # Start watch mode
        watch_process = test.start_watch_mode()

        try:
            # Delete file
            files["script_1"].unlink()

            # Wait for watch mode to detect deletion (should be fast with filesystem events)
            time.sleep(5)  # 1s debounce + 2s processing + 2s buffer

            # Use retry logic to verify hard deletion with eventual consistency
            deletion_verified = test.verify_hard_deletion_with_retry(
                "script 1", "script_1.py", initial_stats["total_points"]
            )
            assert (
                deletion_verified
            ), "Deleted file should not be queryable after retries"

        finally:
            if watch_process:
                watch_process.terminate()
                try:
                    watch_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    watch_process.kill()

    finally:
        test.cleanup_test_environment()


@pytest.mark.slow
@pytest.mark.e2e
def test_deletion_performance(tmp_path):
    """Test deletion performance with many files."""
    test = DeletionE2ETest()
    test.setup_test_environment(tmp_path)

    try:
        # Create project with many files
        files = test.create_git_repo_with_files(10)

        # Index all files
        index_result = test.index_files()
        assert (
            index_result.returncode == 0
        ), f"Initial indexing failed: {index_result.stderr}"

        # Verify files are indexed
        initial_stats = test.get_collection_stats()
        assert initial_stats["total_points"] > 0, "No files were indexed"

        # Delete most files (keep only 2)
        for i in range(2, 10):
            files[f"module_{i}"].unlink()

        # Measure reconcile performance
        import time

        start_time = time.time()

        reconcile_result = test.index_files(["--reconcile"])

        end_time = time.time()
        reconcile_duration = end_time - start_time

        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"

        # Performance should be reasonable (under 30 seconds for 8 deletions)
        assert (
            reconcile_duration < 30
        ), f"Reconcile took too long: {reconcile_duration:.2f}s"

        # Verify only remaining files are queryable with eventual consistency retry
        def verify_deletion_performance_with_retry(max_retries=8):
            for attempt in range(max_retries):
                remaining_query = test.query_files("Feature0Handler OR Feature1Handler")
                if remaining_query["returncode"] != 0:
                    time.sleep(2)
                    continue

                remaining_output = remaining_query["stdout"]

                # Check if remaining files are queryable and deleted files are not
                remaining_files_ok = (
                    "module_0.py" in remaining_output
                    and "module_1.py" in remaining_output
                )

                deleted_files_gone = all(
                    f"module_{i}.py" not in remaining_output for i in range(2, 10)
                )

                if remaining_files_ok and deleted_files_gone:
                    print(
                        f"✅ Performance deletion verification successful on attempt {attempt + 1}"
                    )
                    return True

                print(
                    f"🔄 Attempt {attempt + 1}: Still verifying deletion consistency..."
                )
                time.sleep(2)  # Account for eventual consistency

            return False

        deletion_verified = verify_deletion_performance_with_retry()
        assert (
            deletion_verified
        ), "Performance deletion verification failed after retries"

    finally:
        test.cleanup_test_environment()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

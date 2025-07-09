"""
Test to reproduce stuck behavior specifically in the verification retry logic.

This test targets the specific issue where verification retries cause stuck behavior
when processing deleted files, particularly in watch mode scenarios.
"""

import time
import subprocess
from pathlib import Path
import pytest

from .conftest import local_temporary_directory
from .test_infrastructure import (
    auto_register_project_collections,
)


@pytest.fixture
def stuck_verification_test_repo():
    """Create a test repository for stuck verification retry tests."""
    with local_temporary_directory() as temp_dir:
        # Auto-register collections for cleanup
        auto_register_project_collections(temp_dir)

        # Preserve .code-indexer directory if it exists
        config_dir = temp_dir / ".code-indexer"
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)

        yield temp_dir


def create_git_repo_with_files(base_dir: Path) -> Path:
    """Create a git repository with initial files."""
    repo_dir = base_dir

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
    )

    # Create initial files
    files_to_create = [
        ("main.py", "print('Hello World')"),
        ("config.py", "DEBUG = True"),
        ("utils.py", "def helper(): return 'helper'"),
    ]

    for file_path, content in files_to_create:
        full_path = repo_dir / file_path
        full_path.write_text(content)

    # Commit initial files
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return repo_dir


def start_watch_mode(test_repo_dir: Path) -> subprocess.Popen:
    """Start watch mode in background."""
    cmd = ["code-indexer", "watch"]
    process = subprocess.Popen(
        cmd,
        cwd=test_repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Give watch mode a moment to start
    time.sleep(2)
    return process


@pytest.mark.slow
@pytest.mark.skipif(
    not pytest.importorskip("qdrant_client", reason="Qdrant client not available")
)
def test_watch_mode_deletion_with_verification_retry(stuck_verification_test_repo):
    """
    Test watch mode deletion handling with verification retry logic.

    This test focuses on the specific scenario where watch mode processes
    deleted files and gets stuck in verification retry loops.
    """
    test_repo_dir = stuck_verification_test_repo
    watch_process = None

    try:
        print("\n🎯 Testing watch mode deletion with verification retry")

        # Setup test repository
        create_git_repo_with_files(test_repo_dir)
        print(f"✅ Created test git repository at: {test_repo_dir}")

        # Initialize code-indexer
        init_result = subprocess.run(
            ["code-indexer", "init", "--embedding-provider", "ollama"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Perform initial indexing
        initial_index_result = subprocess.run(
            ["code-indexer", "index"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            initial_index_result.returncode == 0
        ), f"Initial indexing failed: {initial_index_result.stderr}"
        print("✅ Initial indexing completed")

        # Start watch mode
        print("🔍 Starting watch mode...")
        watch_process = start_watch_mode(test_repo_dir)

        # Verify watch mode started
        time.sleep(3)
        if watch_process.poll() is not None:
            stdout, stderr = watch_process.communicate()
            pytest.fail(f"Watch mode failed to start: {stderr}")

        print("✅ Watch mode started successfully")

        # Now delete files while watch mode is running
        print("🗑️  Deleting files while watch mode is active...")
        files_to_delete = ["utils.py", "config.py"]

        for file_path in files_to_delete:
            full_path = test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()
                print(f"   Deleted: {file_path}")

                # Give watch mode time to detect and process the deletion
                # This is where the verification retry logic should trigger
                time.sleep(2)

        # Commit deletions
        subprocess.run(
            ["git", "add", "."], cwd=test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Delete files in watch mode"],
            cwd=test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Monitor watch mode output for a period to see if it gets stuck
        print("⏱️  Monitoring watch mode for stuck behavior...")
        monitor_duration = 15  # Monitor for 15 seconds
        start_time = time.time()

        while time.time() - start_time < monitor_duration:
            if watch_process.poll() is not None:
                # Watch mode exited
                stdout, stderr = watch_process.communicate()
                print(f"Watch mode exited unexpectedly: {stderr}")
                break

            # Check for output that might indicate stuck behavior
            # This is a simplified check - in real scenarios we'd need more sophisticated monitoring
            time.sleep(1)

        # Terminate watch mode
        print("🛑 Terminating watch mode...")
        watch_process.terminate()

        try:
            stdout, stderr = watch_process.communicate(timeout=5)
            print(f"Watch mode output: {stdout[-500:] if stdout else 'No stdout'}")
            if stderr:
                print(f"Watch mode errors: {stderr[-500:]}")
        except subprocess.TimeoutExpired:
            print("⚠️  Watch mode didn't terminate gracefully, killing...")
            watch_process.kill()
            stdout, stderr = watch_process.communicate()

        # Verify that deletions were processed correctly
        print("🔍 Verifying deletion processing...")
        query_result = subprocess.run(
            ["code-indexer", "query", "helper function"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if query_result.returncode == 0:
            # Check if deleted files still appear in results
            for deleted_file in files_to_delete:
                if deleted_file in query_result.stdout:
                    print(
                        f"⚠️  Deleted file {deleted_file} still appears in query results"
                    )
                    print(f"Query output: {query_result.stdout}")
                else:
                    print(f"✅ Deleted file {deleted_file} properly removed from index")

        print("✅ Watch mode deletion test completed")

    finally:
        if watch_process and watch_process.poll() is None:
            watch_process.terminate()
            try:
                watch_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                watch_process.kill()


@pytest.mark.slow
@pytest.mark.skipif(
    not pytest.importorskip("qdrant_client", reason="Qdrant client not available")
)
def test_direct_verification_retry_behavior(stuck_verification_test_repo):
    """
    Test the verification retry behavior directly by calling internal methods.

    This test attempts to reproduce the stuck behavior by directly testing
    the verification retry logic that might be causing the issue.
    """
    test_repo_dir = stuck_verification_test_repo

    print("\n🔬 Testing direct verification retry behavior")

    # Setup test repository
    create_git_repo_with_files(test_repo_dir)

    # Initialize and start services
    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "ollama"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert init_result.returncode == 0

    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert start_result.returncode == 0

    # Perform initial indexing
    initial_index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert initial_index_result.returncode == 0

    # Delete a file
    file_to_delete = "utils.py"
    full_path = test_repo_dir / file_to_delete
    full_path.unlink()

    # Commit the deletion
    subprocess.run(
        ["git", "add", "."], cwd=test_repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Delete file for verification test"],
        cwd=test_repo_dir,
        check=True,
        capture_output=True,
    )

    # Now try to trigger the verification retry logic by using incremental indexing
    # with deletion detection multiple times in quick succession
    print("🔄 Running multiple deletion detection cycles...")

    for i in range(3):
        print(f"   Cycle {i + 1}/3")
        start_time = time.time()

        result = subprocess.run(
            ["code-indexer", "index", "--detect-deletions"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        duration = time.time() - start_time
        print(f"   Duration: {duration:.2f}s")

        if result.returncode != 0:
            print(f"   Error: {result.stderr}")
        else:
            print(
                f"   Success: {result.stdout[-200:] if result.stdout else 'No output'}"
            )

        # Check if any cycle takes significantly longer (indicating stuck behavior)
        if duration > 10:  # If any cycle takes more than 10 seconds
            pytest.fail(
                f"Deletion detection cycle {i + 1} took too long: {duration:.2f}s"
            )

    print("✅ Direct verification retry test completed")


@pytest.mark.slow
@pytest.mark.skipif(
    not pytest.importorskip("qdrant_client", reason="Qdrant client not available")
)
def test_performance_with_many_deletions(stuck_verification_test_repo):
    """
    Test performance impact of verification retry logic with many deletions.

    This test creates many files, deletes them, and measures if the verification
    retry logic causes performance degradation.
    """
    test_repo_dir = stuck_verification_test_repo

    print("\n📊 Testing performance impact with many deletions")

    # Setup test repository
    create_git_repo_with_files(test_repo_dir)

    # Create many additional files
    print("📝 Creating many files...")
    for i in range(50):  # Create 50 files
        file_path = f"file_{i:03d}.py"
        content = f"# File {i}\ndef function_{i}(): return {i}"
        full_path = test_repo_dir / file_path
        full_path.write_text(content)

    # Commit all files
    subprocess.run(
        ["git", "add", "."], cwd=test_repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Add many files"],
        cwd=test_repo_dir,
        check=True,
        capture_output=True,
    )

    # Initialize and index
    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "ollama"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert init_result.returncode == 0

    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert start_result.returncode == 0

    initial_index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert initial_index_result.returncode == 0
    print("✅ Initial indexing of many files completed")

    # Delete many files
    print("🗑️  Deleting many files...")
    deleted_count = 0
    for i in range(0, 50, 2):  # Delete every other file
        file_path = f"file_{i:03d}.py"
        full_path = test_repo_dir / file_path
        if full_path.exists():
            full_path.unlink()
            deleted_count += 1

    # Also delete original files
    for file_path in ["utils.py", "config.py"]:
        full_path = test_repo_dir / file_path
        if full_path.exists():
            full_path.unlink()
            deleted_count += 1

    subprocess.run(
        ["git", "add", "."], cwd=test_repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", f"Delete {deleted_count} files"],
        cwd=test_repo_dir,
        check=True,
        capture_output=True,
    )

    print(f"📊 Deleted {deleted_count} files")

    # Measure deletion detection performance
    print("⏱️  Measuring deletion detection performance...")
    start_time = time.time()

    deletion_result = subprocess.run(
        ["code-indexer", "index", "--detect-deletions"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=120,  # 2 minute timeout
    )

    duration = time.time() - start_time

    print("📊 Deletion detection results:")
    print(f"   Files deleted: {deleted_count}")
    print(f"   Total duration: {duration:.2f}s")
    print(f"   Average per deletion: {duration / deleted_count:.2f}s")
    print(f"   Success: {deletion_result.returncode == 0}")

    if deletion_result.returncode != 0:
        print(f"   Error: {deletion_result.stderr}")

    # Performance assertion
    max_time_per_deletion = 3.0  # 3 seconds per deletion should be reasonable
    avg_time_per_deletion = duration / deleted_count

    if avg_time_per_deletion > max_time_per_deletion:
        print(
            f"❌ Performance issue detected: {avg_time_per_deletion:.2f}s per deletion"
        )
        print("   This suggests the verification retry logic may be causing delays")

        # This would be the failing assertion that proves the performance issue
        pytest.fail(
            f"Deletion processing too slow: {avg_time_per_deletion:.2f}s per file "
            f"(limit: {max_time_per_deletion}s per file). "
            f"This indicates the verification retry logic is causing performance issues."
        )
    else:
        print(f"✅ Performance acceptable: {avg_time_per_deletion:.2f}s per deletion")

    print("✅ Performance test completed")

"""
Test to reproduce deadlock in incremental indexing on deleted files.

This test specifically targets deadlock conditions where the verification
retry logic gets stuck in an infinite wait, never completing.

Key deadlock scenarios to test:
1. Verification method gets stuck waiting for Qdrant response
2. Retry loop continues indefinitely because verification never succeeds
3. Race conditions between deletion and verification
"""

import time
import subprocess
from pathlib import Path
import pytest

from .conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def deadlock_test_repo():
    """Create a test repository for deadlock reproduction tests."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.DEADLOCK_REPRODUCTION
        )

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

    # Create files that might cause issues during deletion
    files_to_create = [
        (
            "main.py",
            "def main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()",
        ),
        (
            "utils.py",
            "def helper_function():\n    return 'helper'\n\ndef another_helper():\n    return 'another'",
        ),
        (
            "config.py",
            "DATABASE_URL = 'sqlite:///app.db'\nDEBUG = True\nSECRET_KEY = 'dev-key'",
        ),
        (
            "models.py",
            "class User:\n    def __init__(self, name):\n        self.name = name\n\nclass Product:\n    def __init__(self, name, price):\n        self.name = name\n        self.price = price",
        ),
        (
            "views.py",
            "def index():\n    return 'Index page'\n\ndef about():\n    return 'About page'",
        ),
    ]

    for file_path, content in files_to_create:
        full_path = repo_dir / file_path
        full_path.write_text(content)

    # Create .gitignore to prevent committing .code-indexer directory
    (repo_dir / ".gitignore").write_text(
        """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
    )

    # Commit initial files
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return repo_dir


def run_with_aggressive_timeout(
    test_repo_dir: Path, command: list, timeout_seconds: int = 10
) -> dict:
    """Run command with aggressive timeout to catch deadlocks quickly."""
    start_time = time.time()

    try:
        result = subprocess.run(
            ["code-indexer"] + command,
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        end_time = time.time()
        duration = end_time - start_time

        return {
            "success": True,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": duration,
            "timed_out": False,
        }

    except subprocess.TimeoutExpired as e:
        end_time = time.time()
        duration = end_time - start_time

        return {
            "success": False,
            "returncode": -1,
            "stdout": e.stdout.decode() if e.stdout else "",
            "stderr": e.stderr.decode() if e.stderr else "",
            "duration": duration,
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
        }


@pytest.mark.slow
@pytest.mark.skipif(
    not pytest.importorskip("qdrant_client", reason="Qdrant client not available")
)
def test_deadlock_with_aggressive_timeout(deadlock_test_repo):
    """
    Test for deadlock with very aggressive timeout.

    This test uses a short timeout to quickly detect if the process
    gets stuck in an infinite wait condition.
    """
    test_repo_dir = deadlock_test_repo

    print("\n💀 Testing for deadlock with aggressive 10-second timeout")

    # Setup test repository
    create_git_repo_with_files(test_repo_dir)
    print(f"✅ Created test git repository at: {test_repo_dir}")

    # Initialize this specific project
    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

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

    # Delete multiple files to trigger potential deadlock
    print("🗑️  Deleting multiple files...")
    files_to_delete = ["utils.py", "models.py", "views.py"]

    for file_path in files_to_delete:
        full_path = test_repo_dir / file_path
        if full_path.exists():
            full_path.unlink()
            print(f"   Deleted: {file_path}")

    # Commit deletions
    subprocess.run(
        ["git", "add", "."], cwd=test_repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Delete files to trigger deadlock"],
        cwd=test_repo_dir,
        check=True,
        capture_output=True,
    )

    # Run incremental indexing with aggressive timeout to catch deadlock
    print("⏱️  Running incremental indexing with 10-second timeout...")
    print("   If this times out, we've reproduced the deadlock!")

    deadlock_result = run_with_aggressive_timeout(
        test_repo_dir,
        ["index", "--detect-deletions"],
        timeout_seconds=10,  # Very aggressive timeout
    )

    # Analyze results
    print("\n📊 Deadlock test results:")
    print(f"   Success: {deadlock_result['success']}")
    print(f"   Duration: {deadlock_result['duration']:.2f}s")
    print(f"   Timed out: {deadlock_result['timed_out']}")
    print(f"   Return code: {deadlock_result['returncode']}")

    if deadlock_result["stdout"]:
        print(f"   Last stdout: {deadlock_result['stdout'][-300:]}")
    if deadlock_result["stderr"]:
        print(f"   Last stderr: {deadlock_result['stderr'][-300:]}")

    if deadlock_result["timed_out"]:
        print("🎯 DEADLOCK REPRODUCED!")
        print(f"   Process hung for {deadlock_result['timeout_seconds']}+ seconds")
        print("   This confirms the reported deadlock issue exists.")

        # This assertion should fail when deadlock is reproduced
        pytest.fail(
            f"DEADLOCK DETECTED: Incremental indexing hung for {deadlock_result['timeout_seconds']}+ seconds. "
            f"Last output: {deadlock_result['stdout'][-200:] if deadlock_result['stdout'] else 'No output'}"
        )
    else:
        print("✅ No deadlock detected - indexing completed normally")
        assert deadlock_result[
            "success"
        ], f"Indexing failed: {deadlock_result['stderr']}"
        assert (
            deadlock_result["returncode"] == 0
        ), f"Indexing returned error: {deadlock_result['returncode']}"


@pytest.mark.slow
@pytest.mark.skipif(
    not pytest.importorskip("qdrant_client", reason="Qdrant client not available")
)
def test_repeated_deletion_cycles_for_deadlock(deadlock_test_repo):
    """
    Test repeated deletion cycles to trigger race conditions.

    This test runs multiple deletion cycles rapidly to increase
    the chance of hitting race conditions that cause deadlock.
    """
    test_repo_dir = deadlock_test_repo

    print("\n🔄 Testing repeated deletion cycles for deadlock")

    # Setup test repository
    create_git_repo_with_files(test_repo_dir)

    # Initialize this specific project
    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert init_result.returncode == 0

    # Perform initial indexing
    initial_index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert initial_index_result.returncode == 0
    print("✅ Initial indexing completed")

    # Run multiple rapid deletion cycles
    for cycle in range(3):
        print(f"\n🔄 Deletion cycle {cycle + 1}/3")

        # Create and delete different files each cycle
        test_files = [
            f"temp_{cycle}_a.py",
            f"temp_{cycle}_b.py",
            f"temp_{cycle}_c.py",
        ]

        # Create files
        for file_name in test_files:
            full_path = test_repo_dir / file_name
            full_path.write_text(f"# Temporary file {file_name}\ndata = {cycle}")

        # Index the new files
        subprocess.run(
            ["git", "add", "."],
            cwd=test_repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Add cycle {cycle} files"],
            cwd=test_repo_dir,
            check=True,
            capture_output=True,
        )

        add_result = run_with_aggressive_timeout(
            test_repo_dir, ["index"], timeout_seconds=15
        )
        if add_result["timed_out"]:
            pytest.fail(f"Deadlock during file addition in cycle {cycle + 1}")

        # Delete files
        for file_name in test_files:
            full_path = test_repo_dir / file_name
            if full_path.exists():
                full_path.unlink()

        subprocess.run(
            ["git", "add", "."],
            cwd=test_repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Delete cycle {cycle} files"],
            cwd=test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Test deletion with aggressive timeout
        delete_result = run_with_aggressive_timeout(
            test_repo_dir, ["index", "--detect-deletions"], timeout_seconds=15
        )

        print(f"   Cycle {cycle + 1} duration: {delete_result['duration']:.2f}s")

        if delete_result["timed_out"]:
            print(f"🎯 DEADLOCK REPRODUCED in cycle {cycle + 1}!")
            pytest.fail(
                f"DEADLOCK in deletion cycle {cycle + 1}: "
                f"Process hung for {delete_result['timeout_seconds']}+ seconds"
            )

    print("✅ All deletion cycles completed without deadlock")


@pytest.mark.slow
@pytest.mark.skipif(
    not pytest.importorskip("qdrant_client", reason="Qdrant client not available")
)
def test_concurrent_operations_deadlock(deadlock_test_repo):
    """
    Test concurrent operations that might trigger deadlock.

    This test simulates conditions where multiple operations
    might interfere with each other and cause deadlock.
    """
    test_repo_dir = deadlock_test_repo

    print("\n⚡ Testing concurrent operations for deadlock")

    # Setup test repository
    create_git_repo_with_files(test_repo_dir)

    # Initialize this specific project
    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert init_result.returncode == 0

    # Perform initial indexing
    initial_index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert initial_index_result.returncode == 0

    # Delete files
    files_to_delete = ["utils.py", "models.py"]
    for file_path in files_to_delete:
        full_path = test_repo_dir / file_path
        if full_path.exists():
            full_path.unlink()

    subprocess.run(
        ["git", "add", "."], cwd=test_repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Delete files for concurrent test"],
        cwd=test_repo_dir,
        check=True,
        capture_output=True,
    )

    # Run deletion detection multiple times rapidly to create race conditions
    print("🏃 Running rapid consecutive deletion detection...")

    for i in range(3):
        print(f"   Rapid run {i + 1}/3")
        rapid_result = run_with_aggressive_timeout(
            test_repo_dir,
            ["index", "--detect-deletions"],
            timeout_seconds=8,  # Even more aggressive timeout
        )

        if rapid_result["timed_out"]:
            print(f"🎯 DEADLOCK REPRODUCED in rapid run {i + 1}!")
            pytest.fail(
                f"DEADLOCK in rapid deletion detection run {i + 1}: "
                f"Process hung for {rapid_result['timeout_seconds']}+ seconds"
            )

        print(f"   Run {i + 1} completed in {rapid_result['duration']:.2f}s")

        # Small delay between runs
        time.sleep(0.5)

    print("✅ Concurrent operations test completed without deadlock")


@pytest.mark.slow
@pytest.mark.skipif(
    not pytest.importorskip("qdrant_client", reason="Qdrant client not available")
)
def test_specific_verification_deadlock(deadlock_test_repo):
    """
    Test specifically targeting the verification retry deadlock.

    This test tries to create conditions where the verification
    method gets stuck in an infinite retry loop.
    """
    test_repo_dir = deadlock_test_repo

    print("\n🔍 Testing verification retry deadlock scenario")

    # Setup with a larger number of files to increase verification complexity
    create_git_repo_with_files(test_repo_dir)

    # Create additional files to make verification more complex
    for i in range(15):  # Create 15 additional files
        file_path = f"extra_{i:02d}.py"
        content = f"# Extra file {i}\ndef function_{i}():\n    return {i}\n\nclass Class{i}:\n    value = {i}"
        full_path = test_repo_dir / file_path
        full_path.write_text(content)

    subprocess.run(
        ["git", "add", "."], cwd=test_repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Add extra files"],
        cwd=test_repo_dir,
        check=True,
        capture_output=True,
    )

    # Initialize this specific project
    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert init_result.returncode == 0

    # Perform initial indexing
    initial_index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert initial_index_result.returncode == 0
    print("✅ Initial indexing with extra files completed")

    # Delete many files at once to stress the verification system
    files_to_delete = ["utils.py", "models.py", "views.py"] + [
        f"extra_{i:02d}.py" for i in range(0, 15, 2)
    ]

    print(f"🗑️  Deleting {len(files_to_delete)} files to stress verification...")
    for file_path in files_to_delete:
        full_path = test_repo_dir / file_path
        if full_path.exists():
            full_path.unlink()

    subprocess.run(
        ["git", "add", "."], cwd=test_repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", f"Delete {len(files_to_delete)} files"],
        cwd=test_repo_dir,
        check=True,
        capture_output=True,
    )

    # Run deletion detection with very aggressive timeout
    print("⏱️  Running deletion detection with 12-second timeout...")
    verification_result = run_with_aggressive_timeout(
        test_repo_dir, ["index", "--detect-deletions"], timeout_seconds=12
    )

    print("\n📊 Verification deadlock test results:")
    print(f"   Files deleted: {len(files_to_delete)}")
    print(f"   Duration: {verification_result['duration']:.2f}s")
    print(f"   Timed out: {verification_result['timed_out']}")

    if verification_result["timed_out"]:
        print("🎯 VERIFICATION DEADLOCK REPRODUCED!")
        print(
            f"   Process hung during verification of {len(files_to_delete)} deletions"
        )

        pytest.fail(
            f"VERIFICATION DEADLOCK: Process hung for {verification_result['timeout_seconds']}+ seconds "
            f"while verifying {len(files_to_delete)} deletions. "
            f"This confirms the verification retry deadlock issue."
        )
    else:
        print("✅ Verification completed without deadlock")
        assert verification_result[
            "success"
        ], f"Verification failed: {verification_result['stderr']}"

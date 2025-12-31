"""
Test that golden repo job results contain alias field for dashboard display.

This test verifies the fix for the dashboard "Unknown" repository bug.
All background job results should include the repository alias so the
dashboard can display the repository name in the Recent Activity section.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager
from code_indexer.server.repositories.background_jobs import BackgroundJobManager


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    golden_repos_dir = temp_dir / "golden-repos"
    job_storage = temp_dir / "jobs"
    golden_repos_dir.mkdir(parents=True)
    job_storage.mkdir(parents=True)

    yield {
        "golden_repos_dir": str(golden_repos_dir),
        "job_storage": str(job_storage / "jobs.json"),
    }

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def managers(temp_dirs):
    """Create manager instances for testing."""
    job_manager = BackgroundJobManager(storage_path=temp_dirs["job_storage"])
    golden_manager = GoldenRepoManager(data_dir=temp_dirs["golden_repos_dir"])

    # Inject background job manager (pattern from test_golden_repo_manager.py)
    golden_manager.background_job_manager = job_manager

    return {
        "job_manager": job_manager,
        "golden_manager": golden_manager,
    }


def test_add_golden_repo_result_contains_alias(managers, temp_dirs):
    """Test that add_golden_repo job result contains alias field."""
    # Create a test repository
    test_repo_path = Path(temp_dirs["golden_repos_dir"]) / "test-repo"
    test_repo_path.mkdir(parents=True)

    # Initialize as git repo
    import subprocess

    subprocess.run(["git", "init"], cwd=test_repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    test_file = test_repo_path / "README.md"
    test_file.write_text("# Test Repo")
    subprocess.run(
        ["git", "add", "."], cwd=test_repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=test_repo_path,
        check=True,
        capture_output=True,
    )

    # Submit add_golden_repo job
    job_id = managers["golden_manager"].add_golden_repo(
        repo_url=str(test_repo_path),
        alias="test-repo",
        submitter_username="test-user",
    )

    # Wait for job completion (synchronously execute for testing)
    import time

    max_wait = 10
    waited = 0
    while waited < max_wait:
        job = managers["job_manager"].jobs.get(job_id)
        if job and job.status.value in ["completed", "failed"]:
            break
        time.sleep(0.1)
        waited += 0.1

    # Verify job completed successfully
    job = managers["job_manager"].jobs.get(job_id)
    assert job is not None, f"Job {job_id} not found"
    assert job.status.value == "completed", f"Job failed: {job.error}"

    # CRITICAL: Verify result contains alias field for dashboard display
    assert job.result is not None, "Job result is None"
    assert (
        "alias" in job.result
    ), "Job result missing 'alias' field - dashboard will show 'Unknown'"
    assert (
        job.result["alias"] == "test-repo"
    ), f"Expected alias 'test-repo', got '{job.result['alias']}'"


def test_refresh_golden_repo_result_contains_alias(managers, temp_dirs):
    """Test that refresh_golden_repo job result contains alias field."""
    # Create and add a test repository first
    test_repo_path = Path(temp_dirs["golden_repos_dir"]) / "refresh-test-repo"
    test_repo_path.mkdir(parents=True)

    # Initialize as git repo
    import subprocess

    subprocess.run(["git", "init"], cwd=test_repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    test_file = test_repo_path / "README.md"
    test_file.write_text("# Refresh Test Repo")
    subprocess.run(
        ["git", "add", "."], cwd=test_repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=test_repo_path,
        check=True,
        capture_output=True,
    )

    # Add repository
    add_job_id = managers["golden_manager"].add_golden_repo(
        repo_url=str(test_repo_path),
        alias="refresh-test-repo",
        submitter_username="test-user",
    )

    # Wait for add job completion
    import time

    max_wait = 10
    waited = 0
    while waited < max_wait:
        job = managers["job_manager"].jobs.get(add_job_id)
        if job and job.status.value in ["completed", "failed"]:
            break
        time.sleep(0.1)
        waited += 0.1

    # Submit refresh job
    refresh_job_id = managers["golden_manager"].refresh_golden_repo(
        alias="refresh-test-repo",
        submitter_username="test-user",
    )

    # Wait for refresh job completion
    waited = 0
    while waited < max_wait:
        job = managers["job_manager"].jobs.get(refresh_job_id)
        if job and job.status.value in ["completed", "failed"]:
            break
        time.sleep(0.1)
        waited += 0.1

    # Verify job completed successfully
    job = managers["job_manager"].jobs.get(refresh_job_id)
    assert job is not None, f"Job {refresh_job_id} not found"
    assert job.status.value == "completed", f"Job failed: {job.error}"

    # CRITICAL: Verify result contains alias field for dashboard display
    assert job.result is not None, "Job result is None"
    assert (
        "alias" in job.result
    ), "Job result missing 'alias' field - dashboard will show 'Unknown'"
    assert (
        job.result["alias"] == "refresh-test-repo"
    ), f"Expected alias 'refresh-test-repo', got '{job.result['alias']}'"

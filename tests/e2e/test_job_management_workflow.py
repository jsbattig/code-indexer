"""
End-to-end tests for Job Management System workflow.

Tests the complete job management functionality including job submission,
status tracking, listing with filters, cancellation, and persistence
across the entire system without any mocking.
"""

import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app


class TestJobManagementWorkflowE2E:
    """End-to-end tests for job management system workflow."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client with real app."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage for job persistence."""
        temp_dir = tempfile.mkdtemp()
        job_storage_path = Path(temp_dir) / "jobs.json"
        yield temp_dir, job_storage_path

        # Clean up
        if job_storage_path.exists():
            job_storage_path.unlink()
        os.rmdir(temp_dir)

    @pytest.fixture
    def authenticated_users(self, client):
        """Create and authenticate test users."""
        users = {}

        # First, login as admin to create test users
        admin_login = {"username": "admin", "password": "admin"}
        response = client.post("/auth/login", json=admin_login)
        assert response.status_code == 200
        admin_token = response.json()["access_token"]
        users["admin"] = admin_token

        # Create test users using admin privileges
        test_users = [
            ("testuser1", "normal_user"),
            ("testuser2", "normal_user"),
            ("adminuser", "admin"),
        ]

        for username, role in test_users:
            # Create user via admin endpoint
            create_user_data = {
                "username": username,
                "password": "TestPass123!",
                "role": role,
            }
            response = client.post(
                "/api/admin/users",
                json=create_user_data,
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            # User might already exist, that's okay
            if response.status_code not in [200, 201, 400]:
                assert False, f"Failed to create user {username}: {response.text}"

            # Login as the created user
            login_data = {"username": username, "password": "TestPass123!"}
            response = client.post("/auth/login", json=login_data)
            assert response.status_code == 200
            users[username] = response.json()["access_token"]

        return users

    def _get_auth_headers(self, token: str) -> Dict[str, str]:
        """Get authorization headers for API requests."""
        return {"Authorization": f"Bearer {token}"}

    def test_complete_job_management_workflow(self, client, authenticated_users):
        """Test complete job management workflow end-to-end."""
        user1_token = authenticated_users["testuser1"]
        user2_token = authenticated_users["testuser2"]
        admin_token = authenticated_users["admin"]  # Use the original admin user

        # Step 1: Submit a golden repository addition job (long-running task)
        job_data = {
            "repo_url": "https://github.com/example/test-repo.git",
            "alias": "test-repo",
            "clone_on_request": True,
        }

        response = client.post(
            "/api/admin/golden-repos",
            json=job_data,
            headers=self._get_auth_headers(admin_token),
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        assert job_id is not None

        # Step 2: Check initial job status
        response = client.get(
            f"/api/jobs/{job_id}", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        job_status = response.json()
        assert job_status["job_id"] == job_id
        assert job_status["status"] in ["pending", "running"]
        assert job_status["username"] == "admin"

        # Step 3: User2 cannot see User1's job (user isolation)
        response = client.get(
            f"/api/jobs/{job_id}", headers=self._get_auth_headers(user2_token)
        )
        assert response.status_code == 404

        # Step 4: List jobs for admin user
        response = client.get("/api/jobs", headers=self._get_auth_headers(admin_token))
        assert response.status_code == 200
        job_list = response.json()
        assert len(job_list["jobs"]) >= 1
        assert job_list["total"] >= 1

        # Find our job in the list
        our_job = None
        for job in job_list["jobs"]:
            if job["job_id"] == job_id:
                our_job = job
                break
        assert our_job is not None
        assert our_job["username"] == "admin"

        # Step 5: Test pagination by submitting more jobs
        additional_job_ids = []
        for i in range(3):
            job_data = {
                "repo_url": f"https://github.com/example/test-repo-{i}.git",
                "alias": f"test-repo-{i}",
                "clone_on_request": True,
            }

            response = client.post(
                "/api/admin/golden-repos",
                json=job_data,
                headers=self._get_auth_headers(admin_token),
            )
            assert response.status_code == 200
            additional_job_ids.append(response.json()["job_id"])

        # Test paginated listing
        response = client.get(
            "/api/jobs?limit=2&offset=0", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        page1 = response.json()
        assert len(page1["jobs"]) == 2
        assert page1["total"] >= 4  # At least our 4 jobs

        response = client.get(
            "/api/jobs?limit=2&offset=2", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        page2 = response.json()
        assert len(page2["jobs"]) >= 2

        # Step 6: Submit another admin job to test user isolation
        job_data_user2 = {
            "repo_url": "https://github.com/example/user2-repo.git",
            "alias": "user2-repo",
            "clone_on_request": True,
        }

        response = client.post(
            "/api/admin/golden-repos",
            json=job_data_user2,
            headers=self._get_auth_headers(admin_token),
        )
        assert response.status_code == 200
        # Job submitted successfully

        # User2 should see no jobs (golden repo jobs require admin)
        response = client.get("/api/jobs", headers=self._get_auth_headers(user2_token))
        assert response.status_code == 200
        user2_jobs = response.json()
        assert len(user2_jobs["jobs"]) == 0  # User2 has no jobs

        # Admin should see their jobs
        response = client.get("/api/jobs", headers=self._get_auth_headers(admin_token))
        assert response.status_code == 200
        admin_jobs = response.json()
        assert len(admin_jobs["jobs"]) >= 2  # At least 2 admin jobs

        # Step 7: Test job cancellation
        # Submit a repository activation job (potentially long-running) as user1
        activation_data = {
            "golden_repo_alias": "test-repo",
            "branch_name": "main",
            "user_alias": "my-test-repo",
        }

        response = client.post(
            "/api/activated-repos",
            json=activation_data,
            headers=self._get_auth_headers(user1_token),
        )
        assert response.status_code == 200
        cancel_job_id = response.json()["job_id"]

        # Try to cancel the job
        response = client.delete(
            f"/api/jobs/{cancel_job_id}", headers=self._get_auth_headers(user1_token)
        )
        assert response.status_code == 200
        cancel_result = response.json()
        assert cancel_result["success"] is True
        assert "cancelled" in cancel_result["message"].lower()

        # Verify job was cancelled
        time.sleep(0.2)  # Allow time for cancellation to process
        response = client.get(
            f"/api/jobs/{cancel_job_id}", headers=self._get_auth_headers(user1_token)
        )
        assert response.status_code == 200
        cancelled_job = response.json()
        assert cancelled_job["status"] == "cancelled"

        # Step 8: User2 cannot cancel admin's job
        response = client.delete(
            f"/api/jobs/{job_id}", headers=self._get_auth_headers(user2_token)
        )
        assert response.status_code == 404

        # Step 9: Test status filtering
        # Wait for jobs to complete or fail
        time.sleep(2.0)

        response = client.get(
            "/api/jobs?status=completed", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        response = client.get(
            "/api/jobs?status=failed", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        response = client.get(
            "/api/jobs?status=cancelled", headers=self._get_auth_headers(user1_token)
        )
        assert response.status_code == 200
        cancelled_jobs = response.json()

        # Should have at least one cancelled job (our cancelled activation)
        assert len(cancelled_jobs["jobs"]) >= 1

        # Step 10: Admin can perform cleanup operations
        response = client.delete(
            "/api/admin/jobs/cleanup?max_age_hours=0",
            headers=self._get_auth_headers(admin_token),
        )
        assert response.status_code == 200
        cleanup_result = response.json()
        assert "cleaned_count" in cleanup_result
        assert cleanup_result["cleaned_count"] >= 0

    def test_job_listing_with_pagination_and_filters(self, client, authenticated_users):
        """Test job listing with pagination and status filtering."""
        admin_token = authenticated_users["admin"]

        # Submit multiple jobs to test pagination
        job_ids = []
        for i in range(5):
            job_data = {
                "repo_url": f"https://github.com/example/pagination-test-{i}.git",
                "alias": f"pagination-test-{i}",
                "clone_on_request": True,
            }

            response = client.post(
                "/api/admin/golden-repos",
                json=job_data,
                headers=self._get_auth_headers(admin_token),
            )
            assert response.status_code == 200
            job_ids.append(response.json()["job_id"])

        # Test pagination
        response = client.get(
            "/api/jobs?limit=2&offset=0", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        page1 = response.json()
        assert len(page1["jobs"]) == 2
        assert page1["total"] >= 5
        assert page1["limit"] == 2
        assert page1["offset"] == 0

        response = client.get(
            "/api/jobs?limit=2&offset=2", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        page2 = response.json()
        assert len(page2["jobs"]) == 2
        assert page2["total"] >= 5
        assert page2["limit"] == 2
        assert page2["offset"] == 2

        # Jobs should be sorted by creation time (newest first)
        if len(page1["jobs"]) > 1:
            job1_time = datetime.fromisoformat(
                page1["jobs"][0]["created_at"].replace("Z", "+00:00")
            )
            job2_time = datetime.fromisoformat(
                page1["jobs"][1]["created_at"].replace("Z", "+00:00")
            )
            assert job1_time >= job2_time

    def test_user_isolation_and_job_cancellation(self, client, authenticated_users):
        """Test user isolation and job cancellation functionality."""
        admin_token = authenticated_users["admin"]
        user2_token = authenticated_users["testuser2"]

        # Admin submits a job
        job_data = {
            "repo_url": "https://github.com/example/isolation-test.git",
            "alias": "isolation-test",
            "clone_on_request": True,
        }

        response = client.post(
            "/api/admin/golden-repos",
            json=job_data,
            headers=self._get_auth_headers(admin_token),
        )
        assert response.status_code == 200
        admin_job_id = response.json()["job_id"]

        # User2 cannot see admin's job
        response = client.get(
            f"/api/jobs/{admin_job_id}", headers=self._get_auth_headers(user2_token)
        )
        assert response.status_code == 404

        # User2 cannot cancel admin's job
        response = client.delete(
            f"/api/jobs/{admin_job_id}", headers=self._get_auth_headers(user2_token)
        )
        assert response.status_code == 404

        # Admin can cancel their own job
        response = client.delete(
            f"/api/jobs/{admin_job_id}", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        cancel_result = response.json()
        assert cancel_result["success"] is True

        # Verify cancellation
        time.sleep(0.1)
        response = client.get(
            f"/api/jobs/{admin_job_id}", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        cancelled_job = response.json()
        assert cancelled_job["status"] == "cancelled"

    def test_admin_cleanup_functionality(self, client, authenticated_users):
        """Test admin job cleanup functionality."""
        admin_token = authenticated_users["admin"]

        # Submit a job that will complete quickly
        job_data = {
            "repo_url": "https://github.com/example/cleanup-test.git",
            "alias": "cleanup-test",
            "clone_on_request": True,
        }

        response = client.post(
            "/api/admin/golden-repos",
            json=job_data,
            headers=self._get_auth_headers(admin_token),
        )
        assert response.status_code == 200
        # Job submitted for cleanup test

        # Wait for job to complete or fail
        time.sleep(1.0)

        # Admin can perform cleanup
        response = client.delete(
            "/api/admin/jobs/cleanup?max_age_hours=0",
            headers=self._get_auth_headers(admin_token),
        )
        assert response.status_code == 200
        cleanup_result = response.json()
        assert "cleaned_count" in cleanup_result
        assert cleanup_result["cleaned_count"] >= 0

    def test_job_metadata_and_progress_tracking(self, client, authenticated_users):
        """Test job metadata storage and progress tracking."""
        admin_token = authenticated_users[
            "admin"
        ]  # Use admin for golden repo operations

        # Submit a golden repo job (requires admin)
        job_data = {
            "repo_url": "https://github.com/octocat/Hello-World.git",  # Use a real, small repo
            "alias": "metadata-test",
            "clone_on_request": True,
        }

        response = client.post(
            "/api/admin/golden-repos",
            json=job_data,
            headers=self._get_auth_headers(admin_token),
        )
        assert response.status_code == 202  # Async job submission returns 202
        job_id = response.json()["job_id"]

        # Check job metadata
        response = client.get(
            f"/api/jobs/{job_id}", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        job_status = response.json()

        # Verify metadata fields
        assert job_status["job_id"] == job_id
        assert job_status["operation_type"] == "add_golden_repo"
        assert job_status["username"] == "admin"
        assert "created_at" in job_status
        assert job_status["created_at"] is not None
        assert "progress" in job_status
        assert isinstance(job_status["progress"], int)
        assert 0 <= job_status["progress"] <= 100

        # Wait a bit and check if progress or status changed
        time.sleep(0.5)

        response = client.get(
            f"/api/jobs/{job_id}", headers=self._get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        updated_status = response.json()

        # Status should be one of the valid states
        assert updated_status["status"] in [
            "pending",
            "running",
            "completed",
            "failed",
            "cancelled",
        ]

        # If job completed or failed, should have completion timestamp
        if updated_status["status"] in ["completed", "failed", "cancelled"]:
            assert "completed_at" in updated_status
            if updated_status["completed_at"] is not None:
                # Should be a valid ISO timestamp
                completion_time = datetime.fromisoformat(
                    updated_status["completed_at"].replace("Z", "+00:00")
                )
                assert isinstance(completion_time, datetime)

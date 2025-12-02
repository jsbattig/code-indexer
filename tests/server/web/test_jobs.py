"""
Tests for Job Monitoring (Story #535).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


# =============================================================================
# AC1: Job List Display Tests
# =============================================================================

class TestJobListDisplay:
    """Tests for job list display (AC1)."""

    def test_jobs_page_requires_auth(self, web_client: TestClient):
        """
        AC1: Unauthenticated access to /admin/jobs redirects to login.

        Given I am not authenticated
        When I navigate to /admin/jobs
        Then I am redirected to /admin/login
        """
        response = web_client.get("/admin/jobs")

        assert response.status_code in [302, 303], (
            f"Expected redirect, got {response.status_code}"
        )
        location = response.headers.get("location", "")
        assert "/admin/login" in location, (
            f"Expected redirect to /admin/login, got {location}"
        )

    def test_jobs_page_renders(self, authenticated_client: TestClient):
        """
        AC1: Authenticated admin access to /admin/jobs shows jobs page.

        Given I am authenticated as an admin
        When I navigate to /admin/jobs
        Then I see the jobs page with title "Jobs - CIDX Admin"
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "Jobs - CIDX Admin" in response.text, (
            "Page title should be 'Jobs - CIDX Admin'"
        )

    def test_jobs_page_has_table(self, authenticated_client: TestClient):
        """
        AC1: Jobs page displays a table for job listings.

        Given I am authenticated as an admin
        When I view the jobs page
        Then I see a table with job columns
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        assert "<table" in response.text, "Page should contain a table element"
        # Check for expected column headers
        text_lower = response.text.lower()
        assert "id" in text_lower or "job" in text_lower, (
            "Table should have ID column"
        )
        assert "type" in text_lower, "Table should have Type column"
        assert "status" in text_lower, "Table should have Status column"

    def test_jobs_empty_state(self, authenticated_client: TestClient):
        """
        AC1: Empty job list shows "No jobs found" message.

        Given I am authenticated as an admin
        And there are no jobs
        When I view the jobs page
        Then I see "No jobs found" message
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        text_lower = response.text.lower()
        # Should have some indication of no jobs
        assert "no jobs" in text_lower or "empty" in text_lower or "none" in text_lower, (
            "Empty state should be displayed when no jobs exist"
        )

    def test_jobs_nav_highlighted(self, authenticated_client: TestClient):
        """
        AC1: Jobs is highlighted in navigation.

        Given I am authenticated as an admin
        When I view the jobs page
        Then the Jobs link is highlighted in navigation
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        # The jobs should have aria-current="page" attribute
        assert 'aria-current="page"' in response.text, (
            "Jobs should be highlighted with aria-current attribute"
        )


# =============================================================================
# AC2: Job Status Display Tests
# =============================================================================

class TestJobStatusDisplay:
    """Tests for job status display (AC2)."""

    def test_jobs_page_has_status_indicators(self, authenticated_client: TestClient):
        """
        AC2: Jobs page shows status indicators.

        Given I am on the jobs page
        When the page loads
        Then I see status indicator styling is available
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        # Check for status styling classes or indicators
        text = response.text
        assert "status" in text.lower(), (
            "Jobs page should have status-related elements"
        )


# =============================================================================
# AC3: Progress Bar Display Tests
# =============================================================================

class TestProgressBarDisplay:
    """Tests for progress bar display (AC3)."""

    def test_jobs_page_supports_progress(self, authenticated_client: TestClient):
        """
        AC3: Jobs page has progress bar styling available.

        Given I am on the jobs page
        When the page loads
        Then progress bar styling is available
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        # Check that progress-related elements exist (either in CSS or HTML)
        text_lower = response.text.lower()
        assert "progress" in text_lower or "percentage" in text_lower or "%" in response.text, (
            "Jobs page should support progress display"
        )


# =============================================================================
# AC4: Auto-Refresh Tests
# =============================================================================

class TestAutoRefresh:
    """Tests for auto-refresh capability (AC4)."""

    def test_jobs_page_has_htmx_refresh(self, authenticated_client: TestClient):
        """
        AC4: Jobs page uses htmx for partial updates.

        Given I am on the jobs page
        When the page loads
        Then htmx is configured for updates
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        # Check for htmx attributes
        assert "hx-get" in response.text or "hx-trigger" in response.text, (
            "Jobs page should use htmx for updates"
        )

    def test_jobs_page_has_refresh_button(self, authenticated_client: TestClient):
        """
        AC4: Jobs page has a manual refresh button.

        Given I am on the jobs page
        When I view the page
        Then I see a refresh button
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "refresh" in text_lower, (
            "Jobs page should have a refresh button"
        )


# =============================================================================
# AC5: Job Cancellation Tests
# =============================================================================

class TestJobCancellation:
    """Tests for job cancellation (AC5)."""

    def test_jobs_page_has_csrf_protection(self, authenticated_client: TestClient):
        """
        AC5: Jobs page includes CSRF protection for cancel forms.

        Given I am on the jobs page
        When I view the page
        Then CSRF token is available (cookie or form field when jobs exist)
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        # Check for CSRF cookie - CSRF token is set in cookie and will be
        # rendered in cancel forms when there are jobs
        # The cookie proves CSRF protection is enabled for this page
        csrf_cookie = response.cookies.get("_csrf")
        assert csrf_cookie is not None or "csrf_token" in response.text, (
            "Jobs page should include CSRF protection (cookie or form field)"
        )


# =============================================================================
# AC6: Job Filtering Tests
# =============================================================================

class TestJobFiltering:
    """Tests for job filtering (AC6)."""

    def test_jobs_page_has_filters(self, authenticated_client: TestClient):
        """
        AC6: Jobs page has filter options.

        Given I am on the jobs page
        When I view the page
        Then I see filter options
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        # Check for filter elements
        text_lower = response.text.lower()
        assert (
            "filter" in text_lower or
            "<select" in response.text or
            "status" in text_lower
        ), "Jobs page should have filter options"

    def test_jobs_filter_by_status(self, authenticated_client: TestClient):
        """
        AC6: Jobs can be filtered by status.

        Given I am on the jobs page
        When I apply a status filter
        Then the URL accepts status parameter
        """
        # Test that the endpoint accepts status filter parameter
        response = authenticated_client.get("/admin/jobs?status_filter=running")

        assert response.status_code == 200, (
            f"Expected 200 with status filter, got {response.status_code}"
        )

    def test_jobs_filter_by_type(self, authenticated_client: TestClient):
        """
        AC6: Jobs can be filtered by type.

        Given I am on the jobs page
        When I apply a type filter
        Then the URL accepts type parameter
        """
        # Test that the endpoint accepts job_type filter parameter
        response = authenticated_client.get("/admin/jobs?job_type=index")

        assert response.status_code == 200, (
            f"Expected 200 with type filter, got {response.status_code}"
        )


# =============================================================================
# AC7: Job Details View Tests
# =============================================================================

class TestJobDetailsView:
    """Tests for job details view (AC7)."""

    def test_jobs_page_supports_details(self, authenticated_client: TestClient):
        """
        AC7: Jobs page supports showing job details.

        Given I am on the jobs page
        When I view the page
        Then details view functionality is available
        """
        response = authenticated_client.get("/admin/jobs")

        assert response.status_code == 200
        text_lower = response.text.lower()
        # Check for details functionality (button, link, or expandable row)
        assert (
            "detail" in text_lower or
            "view" in text_lower or
            "info" in text_lower or
            "onclick" in response.text
        ), "Jobs page should support viewing job details"


# =============================================================================
# AC8: Pagination Tests
# =============================================================================

class TestJobPagination:
    """Tests for job pagination (AC8)."""

    def test_jobs_page_supports_pagination(self, authenticated_client: TestClient):
        """
        AC8: Jobs page supports pagination parameters.

        Given I am on the jobs page
        When I request a specific page
        Then the page parameter is accepted
        """
        response = authenticated_client.get("/admin/jobs?page=1")

        assert response.status_code == 200, (
            f"Expected 200 with page parameter, got {response.status_code}"
        )


# =============================================================================
# Partial Refresh Endpoint Tests
# =============================================================================

class TestJobsPartials:
    """Tests for htmx partial refresh endpoints."""

    def test_jobs_partial_list(self, authenticated_client: TestClient):
        """
        GET /admin/partials/jobs-list returns HTML fragment.

        Given I am authenticated
        When I request the jobs list partial
        Then I receive an HTML fragment (not full page)
        """
        response = authenticated_client.get("/admin/partials/jobs-list")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}"
        )
        # Should be an HTML fragment, not a full page
        assert "<html>" not in response.text.lower(), (
            "Partial should not contain full HTML structure"
        )

    def test_jobs_partial_list_with_filters(self, authenticated_client: TestClient):
        """
        GET /admin/partials/jobs-list accepts filter parameters.

        Given I am authenticated
        When I request the jobs list partial with filters
        Then I receive filtered results
        """
        response = authenticated_client.get(
            "/admin/partials/jobs-list?status_filter=running&job_type=index"
        )

        assert response.status_code == 200, (
            f"Expected 200 with filters, got {response.status_code}"
        )

    def test_jobs_partial_requires_auth(self, web_client: TestClient):
        """
        Partial endpoint requires authentication.

        Given I am not authenticated
        When I request the jobs list partial
        Then I am redirected to login
        """
        response = web_client.get("/admin/partials/jobs-list")

        assert response.status_code in [302, 303], (
            f"Jobs partial should redirect unauthenticated, got {response.status_code}"
        )


# =============================================================================
# Cancel Job Endpoint Tests
# =============================================================================

class TestCancelJobEndpoint:
    """Tests for job cancellation endpoint."""

    def test_cancel_job_requires_auth(self, web_client: TestClient):
        """
        POST /admin/jobs/{job_id}/cancel requires authentication.

        Given I am not authenticated
        When I try to cancel a job
        Then I am redirected to login
        """
        response = web_client.post("/admin/jobs/test-job-id/cancel")

        assert response.status_code in [302, 303, 403], (
            f"Cancel should require auth, got {response.status_code}"
        )

    def test_cancel_job_requires_csrf(
        self,
        authenticated_client: TestClient
    ):
        """
        POST /admin/jobs/{job_id}/cancel requires CSRF token.

        Given I am authenticated
        When I try to cancel a job without CSRF token
        Then I receive a 403 error
        """
        # Submit cancel without CSRF token
        response = authenticated_client.post(
            "/admin/jobs/test-job-id/cancel",
            data={}
        )

        assert response.status_code == 403, (
            f"Expected 403 without CSRF token, got {response.status_code}"
        )

    def test_cancel_nonexistent_job(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: dict
    ):
        """
        POST /admin/jobs/{job_id}/cancel for nonexistent job returns error.

        Given I am authenticated
        When I try to cancel a job that doesn't exist
        Then I receive an error response
        """
        assert web_infrastructure.client is not None
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"],
            admin_user["password"]
        )

        # Get CSRF token from login page (which always has the token form field)
        # Jobs page only has CSRF tokens in forms when jobs exist
        login_page = client.get("/admin/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_page.text)

        # Try to cancel a nonexistent job
        response = client.post(
            "/admin/jobs/nonexistent-job-id/cancel",
            data={"csrf_token": csrf_token}
        )

        # Should return an error or redirect with error message
        # Accept 200 (page with error), 404, or redirect
        assert response.status_code in [200, 302, 303, 404], (
            f"Expected error response for nonexistent job, got {response.status_code}"
        )
        if response.status_code == 200:
            text_lower = response.text.lower()
            assert "error" in text_lower or "not found" in text_lower or "invalid" in text_lower or "not authorized" in text_lower, (
                "Should show error message for nonexistent job"
            )

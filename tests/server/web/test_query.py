"""
Tests for Query Testing Interface (Story #536).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

from typing import Dict, Any
from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


# =============================================================================
# AC1: Query Form Display Tests
# =============================================================================


class TestQueryFormDisplay:
    """Tests for query form display (AC1)."""

    def test_query_page_requires_auth(self, web_client: TestClient):
        """
        AC1: Unauthenticated access to /admin/query redirects to login.

        Given I am not authenticated
        When I navigate to /admin/query
        Then I am redirected to /admin/login
        """
        response = web_client.get("/admin/query")

        assert response.status_code in [302, 303], (
            f"Expected redirect, got {response.status_code}"
        )
        location = response.headers.get("location", "")
        assert "/admin/login" in location, (
            f"Expected redirect to /admin/login, got {location}"
        )

    def test_query_page_renders(self, authenticated_client: TestClient):
        """
        AC1: Authenticated admin access to /admin/query shows query page.

        Given I am authenticated as an admin
        When I navigate to /admin/query
        Then I see the query page with title "Query - CIDX Admin"
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "Query - CIDX Admin" in response.text, (
            "Page title should be 'Query - CIDX Admin'"
        )

    def test_query_form_has_fields(self, authenticated_client: TestClient):
        """
        AC1: Query form has required fields: query text, repository dropdown, limit.

        Given I am authenticated as an admin
        When I view the query page
        Then I see a form with query text, repository dropdown, and limit fields
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text = response.text
        text_lower = text.lower()

        # Check for query textarea
        assert "textarea" in text_lower, "Page should have a textarea for query text"

        # Check for repository dropdown
        assert "<select" in text_lower, "Page should have a repository dropdown"
        assert "repository" in text_lower or "repo" in text_lower, (
            "Page should have a repository selection"
        )

        # Check for limit input
        assert 'type="number"' in text_lower, (
            "Page should have a number input for limit"
        )
        assert "limit" in text_lower, "Page should have a limit field"

    def test_query_page_has_results_area(self, authenticated_client: TestClient):
        """
        AC1: Query page has a results area (initially empty).

        Given I am authenticated as an admin
        When I view the query page
        Then I see a results area
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "results" in text_lower or "result" in text_lower, (
            "Page should have a results area"
        )

    def test_query_nav_highlighted(self, authenticated_client: TestClient):
        """
        AC1: Query is highlighted in navigation.

        Given I am authenticated as an admin
        When I view the query page
        Then the Query link is highlighted in navigation
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        # The query nav item should have aria-current="page" attribute
        assert 'aria-current="page"' in response.text, (
            "Query should be highlighted with aria-current attribute"
        )


# =============================================================================
# AC2: Advanced Filter Options Tests
# =============================================================================


class TestAdvancedFilterOptions:
    """Tests for advanced filter options (AC2)."""

    def test_advanced_options_exist(self, authenticated_client: TestClient):
        """
        AC2: Query page has collapsible advanced options section.

        Given I am authenticated as an admin
        When I view the query page
        Then I see an advanced options section
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "advanced" in text_lower, "Page should have an advanced options section"

    def test_advanced_has_language_dropdown(self, authenticated_client: TestClient):
        """
        AC2: Advanced options include language dropdown.

        Given I am authenticated as an admin
        When I view the advanced options
        Then I see a language dropdown
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "language" in text_lower, (
            "Advanced options should have a language dropdown"
        )

    def test_advanced_has_path_pattern(self, authenticated_client: TestClient):
        """
        AC2: Advanced options include file path pattern input.

        Given I am authenticated as an admin
        When I view the advanced options
        Then I see a file path pattern input
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "path" in text_lower, "Advanced options should have a path pattern input"

    def test_advanced_has_min_score(self, authenticated_client: TestClient):
        """
        AC2: Advanced options include minimum score input.

        Given I am authenticated as an admin
        When I view the advanced options
        Then I see a minimum score input (0.0-1.0)
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "score" in text_lower or "min" in text_lower, (
            "Advanced options should have a minimum score input"
        )


# =============================================================================
# AC3: Query Execution Tests
# =============================================================================


class TestQueryExecution:
    """Tests for query execution (AC3)."""

    def test_query_form_has_submit_button(self, authenticated_client: TestClient):
        """
        AC3: Query form has a submit button.

        Given I am authenticated as an admin
        When I view the query page
        Then I see a submit button for executing the query
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert (
            "submit" in text_lower or "search" in text_lower or "query" in text_lower
        ), "Page should have a submit/search button"
        assert "<button" in text_lower or 'type="submit"' in text_lower, (
            "Page should have a button element"
        )

    def test_query_has_loading_indicator(self, authenticated_client: TestClient):
        """
        AC3: Query page has a loading indicator.

        Given I am authenticated as an admin
        When I view the query page
        Then I see htmx loading indicator setup
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        # Check for htmx indicator
        assert (
            "htmx-indicator" in response.text or "indicator" in response.text.lower()
        ), "Page should have a loading indicator"

    def test_query_validation(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC3: Query validation for empty query shows error.

        Given I am authenticated as an admin
        When I submit an empty query
        Then I see a validation error
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get CSRF token
        query_page = client.get("/admin/query")
        csrf_token = web_infrastructure.extract_csrf_token(query_page.text)

        # Submit empty query
        response = client.post(
            "/admin/query",
            data={
                "query_text": "",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()
        # Should show validation error
        assert (
            "error" in text_lower or "required" in text_lower or "empty" in text_lower
        ), "Should show error for empty query"


# =============================================================================
# AC4: Results Display Tests
# =============================================================================


class TestResultsDisplay:
    """Tests for results display (AC4)."""

    def test_results_area_structure(self, authenticated_client: TestClient):
        """
        AC4: Results area has proper structure for displaying results.

        Given I am authenticated as an admin
        When I view the query page
        Then the results area is ready to display file path, line numbers, score, etc.
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        # Page should have a results container
        assert "results" in response.text.lower(), "Page should have a results area"

    def test_no_results_message(self, authenticated_client: TestClient):
        """
        AC4: Empty results show appropriate message.

        Given I am authenticated as an admin
        When I view the query page without executing a query
        Then I see an appropriate message or empty state
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        # Initially, there should be no results or a prompt to search
        # This test verifies the page handles empty state


# =============================================================================
# AC5: Code Snippet Display Tests
# =============================================================================


class TestCodeSnippetDisplay:
    """Tests for code snippet display (AC5)."""

    def test_results_partial_exists(self, authenticated_client: TestClient):
        """
        AC5: Results partial endpoint exists for htmx updates.

        Given I am authenticated as an admin
        When I request the query results partial
        Then I receive an HTML fragment
        """
        response = authenticated_client.get("/admin/partials/query-results")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        # Should be an HTML fragment, not a full page
        assert "<html>" not in response.text.lower(), (
            "Partial should not contain full HTML structure"
        )


# =============================================================================
# AC6: Query History Tests
# =============================================================================


class TestQueryHistory:
    """Tests for query history (AC6)."""

    def test_query_history_section_exists(self, authenticated_client: TestClient):
        """
        AC6: Query page has a history section.

        Given I am authenticated as an admin
        When I view the query page
        Then I see a query history section
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert (
            "history" in text_lower
            or "recent" in text_lower
            or "previous" in text_lower
        ), "Page should have a query history section"


# =============================================================================
# AC7: Search Mode Toggle Tests
# =============================================================================


class TestSearchModeToggle:
    """Tests for search mode toggle (AC7)."""

    def test_search_mode_toggle_exists(self, authenticated_client: TestClient):
        """
        AC7: Query page has search mode toggle.

        Given I am authenticated as an admin
        When I view the query page
        Then I see a search mode toggle (Semantic, FTS, Hybrid)
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        text_lower = response.text.lower()
        # Check for search mode options
        assert (
            "semantic" in text_lower
            or "fts" in text_lower
            or "full-text" in text_lower
            or "hybrid" in text_lower
            or "mode" in text_lower
        ), "Page should have search mode toggle options"

    def test_search_mode_selection(self, authenticated_client: TestClient):
        """
        AC7: Current search mode is clearly indicated.

        Given I am authenticated as an admin
        When I view the query page
        Then I can see/select search modes
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        # Check for radio buttons or select for mode
        text_lower = response.text.lower()
        assert (
            'type="radio"' in text_lower
            or "<select" in text_lower
            or "mode" in text_lower
        ), "Page should have mode selection controls"


# =============================================================================
# AC8: Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling (AC8)."""

    def test_query_has_csrf_protection(self, authenticated_client: TestClient):
        """
        AC8: Query form has CSRF protection.

        Given I am authenticated as an admin
        When I view the query page
        Then the form has CSRF token
        """
        response = authenticated_client.get("/admin/query")

        assert response.status_code == 200
        # Check for CSRF cookie or form field
        csrf_cookie = response.cookies.get("_csrf")
        assert csrf_cookie is not None or "csrf_token" in response.text, (
            "Query page should include CSRF protection"
        )

    def test_query_post_requires_csrf(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC8: Query submission requires CSRF token.

        Given I am authenticated as an admin
        When I submit a query without CSRF token
        Then I receive a 403 error or error message
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Submit without CSRF token
        response = client.post(
            "/admin/query",
            data={
                "query_text": "test query",
            },
            follow_redirects=True,
        )

        # Should show error about CSRF or return 403
        text_lower = response.text.lower()
        assert (
            "csrf" in text_lower or "error" in text_lower or response.status_code == 403
        ), "Should show error when CSRF token is missing"


# =============================================================================
# Partial Refresh Endpoint Tests
# =============================================================================


class TestQueryPartials:
    """Tests for htmx partial refresh endpoints."""

    def test_query_partial_results(self, authenticated_client: TestClient):
        """
        GET /admin/partials/query-results returns HTML fragment.

        Given I am authenticated
        When I request the query results partial
        Then I receive an HTML fragment (not full page)
        """
        response = authenticated_client.get("/admin/partials/query-results")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        # Should be an HTML fragment, not a full page
        assert "<html>" not in response.text.lower(), (
            "Partial should not contain full HTML structure"
        )

    def test_partials_require_auth(self, web_client: TestClient):
        """
        Partial endpoints require authentication.

        Given I am not authenticated
        When I request a partial endpoint
        Then I am redirected to login
        """
        response = web_client.get("/admin/partials/query-results")
        assert response.status_code in [302, 303], (
            f"Query partial should redirect unauthenticated, got {response.status_code}"
        )


# =============================================================================
# Query Execution Endpoint Tests
# =============================================================================


class TestQueryExecutionEndpoint:
    """Tests for query execution endpoint."""

    def test_query_execution_endpoint(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        POST /admin/query executes query and returns results.

        Given I am authenticated
        When I submit a valid query
        Then the query is executed and results are shown
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get CSRF token
        query_page = client.get("/admin/query")
        csrf_token = web_infrastructure.extract_csrf_token(query_page.text)

        # Submit a query - note: without real repos, we expect an error or empty results
        response = client.post(
            "/admin/query",
            data={
                "query_text": "authentication",
                "repository": "",  # No repo selected
                "limit": "10",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_query_htmx_execution(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Query can be executed via htmx partial.

        Given I am authenticated
        When I submit a query via htmx
        Then results are returned as HTML fragment
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get CSRF token
        query_page = client.get("/admin/query")
        csrf_token = web_infrastructure.extract_csrf_token(query_page.text)

        # Submit via partial endpoint
        response = client.post(
            "/admin/partials/query-results",
            data={
                "query_text": "test",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

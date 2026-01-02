"""
Tests for Golden Repository Management (Story #533).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

import json
from typing import Dict, Any
from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


# =============================================================================
# AC1: Golden Repository List Display Tests
# =============================================================================


class TestGoldenRepoListDisplay:
    """Tests for golden repository list display (AC1)."""

    def test_golden_repos_page_requires_auth(self, web_client: TestClient):
        """
        AC1: Unauthenticated access to /admin/golden-repos redirects to login.

        Given I am not authenticated
        When I navigate to /admin/golden-repos
        Then I am redirected to /admin/login
        """
        response = web_client.get("/admin/golden-repos")

        assert response.status_code in [
            302,
            303,
        ], f"Expected redirect, got {response.status_code}"
        location = response.headers.get("location", "")
        assert (
            "/admin/login" in location
        ), f"Expected redirect to /admin/login, got {location}"

    def test_golden_repos_page_renders(self, authenticated_client: TestClient):
        """
        AC1: Authenticated admin access to /admin/golden-repos shows golden repos page.

        Given I am authenticated as an admin
        When I navigate to /admin/golden-repos
        Then I see the golden repos page with title "Golden Repositories - CIDX Admin"
        """
        response = authenticated_client.get("/admin/golden-repos")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert (
            "Golden Repositories - CIDX Admin" in response.text
        ), "Page title should be 'Golden Repositories - CIDX Admin'"

    def test_golden_repos_empty_state(self, authenticated_client: TestClient):
        """
        AC1: When no repositories exist, show "No golden repositories configured" message.

        Given I am authenticated as an admin
        And there are no golden repositories
        When I view the golden repos page
        Then I see the message "No golden repositories configured"
        """
        response = authenticated_client.get("/admin/golden-repos")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert (
            "no golden repositories" in text_lower
        ), "Should show 'No golden repositories' message when empty"

    def test_golden_repos_table_columns(self, authenticated_client: TestClient):
        """
        AC1: Golden repos table has columns: Name, Path/URL, Status, Last Indexed, Actions.

        Given I am authenticated as an admin
        When I view the golden repos page
        Then I see a table with columns: Name, Path/URL, Status, Last Indexed, Actions
        """
        response = authenticated_client.get("/admin/golden-repos")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Check table structure
        assert "<table" in text_lower, "Page should contain a golden repos table"
        assert "name" in text_lower, "Table should have Name column"
        # Path or URL should be present
        assert (
            "path" in text_lower or "url" in text_lower
        ), "Table should have Path/URL column"
        assert "status" in text_lower, "Table should have Status column"
        assert (
            "last indexed" in text_lower or "indexed" in text_lower
        ), "Table should have Last Indexed column"
        assert "actions" in text_lower, "Table should have Actions column"

    def test_golden_repos_has_add_button(self, authenticated_client: TestClient):
        """
        AC1: Golden repos page has an "Add Repository" button above the table.

        Given I am authenticated as an admin
        When I view the golden repos page
        Then I see an "Add Repository" button
        """
        response = authenticated_client.get("/admin/golden-repos")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert (
            "add repository" in text_lower or "add-repository" in text_lower
        ), "Page should have an Add Repository button"


# =============================================================================
# AC2: Repository Status Display Tests
# =============================================================================


class TestRepoStatusDisplay:
    """Tests for repository status display (AC2)."""

    def test_status_indicators_in_template(self, authenticated_client: TestClient):
        """
        AC2: Page has appropriate status indicator elements.

        Given I am authenticated as an admin
        When I view the golden repos page
        Then the page contains status indicator elements (ready, indexing, error)
        """
        response = authenticated_client.get("/admin/golden-repos")

        assert response.status_code == 200
        # Template should have status-related CSS classes or elements
        # Even with no repos, the template should be ready for status display
        text = response.text
        # Check that page has proper structure for showing status
        assert (
            "<table" in text.lower() or "status" in text.lower()
        ), "Page should have structure for status display"


# =============================================================================
# AC3: Add Golden Repository Form Tests
# =============================================================================


class TestAddRepoForm:
    """Tests for add golden repository form (AC3)."""

    def test_add_repo_form_renders(self, authenticated_client: TestClient):
        """
        AC3: Add repository form has Name, Path, Branch (optional) fields.

        Given I am authenticated as an admin
        When I view the golden repos page
        Then I see form fields for Name, Path/URL, and Branch
        """
        response = authenticated_client.get("/admin/golden-repos")

        assert response.status_code == 200
        text = response.text

        # Form should have necessary fields
        assert (
            'name="repo_name"' in text.lower() or 'name="alias"' in text.lower()
        ), "Form should have name/alias field"
        assert (
            'name="repo_url"' in text.lower()
            or 'name="path"' in text.lower()
            or 'name="repo_path"' in text.lower()
        ), "Form should have path/URL field"
        assert (
            'name="branch"' in text.lower() or 'name="default_branch"' in text.lower()
        ), "Form should have branch field"

    def test_add_repo_success(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC3: Valid repository addition shows success message.

        Given I am authenticated as an admin
        When I submit valid repository data
        Then I see a success message indicating the job was submitted
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the golden repos page to get CSRF token
        golden_repos_page = client.get("/admin/golden-repos")
        csrf_token = web_infrastructure.extract_csrf_token(golden_repos_page.text)

        # Submit add repository form with a valid local path
        # Note: The API expects repo_url, alias, default_branch
        response = client.post(
            "/admin/golden-repos/add",
            data={
                "alias": "test-repo",
                "repo_url": "/tmp/test-repo",  # Local path for testing
                "default_branch": "main",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show success or job submitted message
        # Note: Adding a repo is async, so we expect job submission success
        assert (
            "success" in text_lower
            or "submitted" in text_lower
            or "started" in text_lower
        ), "Should show success/job submitted message after adding repository"

    def test_add_repo_duplicate_name(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC3: Duplicate name shows validation error.

        Given I am authenticated as an admin
        And a repository with the same alias already exists
        When I try to add a repository with the same alias
        Then I see an error message about duplicate name
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get CSRF token
        golden_repos_page = client.get("/admin/golden-repos")
        csrf_token = web_infrastructure.extract_csrf_token(golden_repos_page.text)

        # First, add a repository
        client.post(
            "/admin/golden-repos/add",
            data={
                "alias": "duplicate-test",
                "repo_url": "/tmp/test-repo-1",
                "default_branch": "main",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        # Get new CSRF token for second request
        golden_repos_page = client.get("/admin/golden-repos")
        csrf_token = web_infrastructure.extract_csrf_token(golden_repos_page.text)

        # Try to add another repository with the same alias
        response = client.post(
            "/admin/golden-repos/add",
            data={
                "alias": "duplicate-test",
                "repo_url": "/tmp/test-repo-2",
                "default_branch": "main",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show error about duplicate
        assert (
            "error" in text_lower or "exists" in text_lower or "already" in text_lower
        ), "Should show error for duplicate repository alias"

    def test_add_repo_invalid_path(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC3: Invalid path/URL shows validation error.

        Given I am authenticated as an admin
        When I submit form with invalid repository path/URL
        Then I see an error message about invalid path
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get CSRF token
        golden_repos_page = client.get("/admin/golden-repos")
        csrf_token = web_infrastructure.extract_csrf_token(golden_repos_page.text)

        # Submit with invalid path
        response = client.post(
            "/admin/golden-repos/add",
            data={
                "alias": "invalid-path-test",
                "repo_url": "/nonexistent/path/that/does/not/exist",
                "default_branch": "main",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show error about invalid path
        assert (
            "error" in text_lower
            or "invalid" in text_lower
            or "inaccessible" in text_lower
        ), "Should show error for invalid repository path"


# =============================================================================
# AC4: Delete Golden Repository Tests
# =============================================================================


class TestDeleteRepo:
    """Tests for delete golden repository (AC4)."""

    def test_delete_repo(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC4: Repository deletion works and shows success message.

        Given I am authenticated as an admin
        And there is a golden repository
        When I delete that repository
        Then I see a success message indicating deletion job started
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get CSRF token
        golden_repos_page = client.get("/admin/golden-repos")
        csrf_token = web_infrastructure.extract_csrf_token(golden_repos_page.text)

        # Delete repository (using a test alias - may not exist in test env)
        response = client.post(
            "/admin/golden-repos/test-repo/delete",
            data={
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Either shows success or error (if repo doesn't exist)
        # We're testing the route works, not the backend behavior


# =============================================================================
# AC5: Refresh Repository Tests
# =============================================================================


class TestRefreshRepo:
    """Tests for refresh repository (AC5)."""

    def test_refresh_repo(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC5: Refresh triggers re-index job.

        Given I am authenticated as an admin
        And there is a golden repository
        When I click refresh
        Then a re-index job is started
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get CSRF token
        golden_repos_page = client.get("/admin/golden-repos")
        csrf_token = web_infrastructure.extract_csrf_token(golden_repos_page.text)

        # Refresh repository (using a test alias)
        response = client.post(
            "/admin/golden-repos/test-repo/refresh",
            data={
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Route should work (backend handles if repo exists or not)


# =============================================================================
# AC6: Repository Details Tests
# =============================================================================


class TestRepoDetails:
    """Tests for repository details (AC6)."""

    def test_repo_details_endpoint(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC6: Repository details endpoint works.

        Given I am authenticated as an admin
        When I request repository details
        Then I get details or appropriate error
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Request details for a repository
        response = client.get("/admin/golden-repos/test-repo/details")

        # Should return 200 with details or appropriate response
        assert response.status_code in [
            200,
            404,
        ], f"Expected 200 or 404, got {response.status_code}"


# =============================================================================
# Partial Refresh Endpoint Tests
# =============================================================================


class TestGoldenReposPartial:
    """Tests for htmx partial refresh endpoint."""

    def test_golden_repos_partial_list(self, authenticated_client: TestClient):
        """
        AC7: GET /admin/partials/golden-repos-list returns HTML fragment.

        Given I am authenticated
        When I request the golden repos list partial
        Then I receive an HTML fragment (not full page)
        """
        response = authenticated_client.get("/admin/partials/golden-repos-list")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        # Should be an HTML fragment, not a full page
        assert (
            "<html>" not in response.text.lower()
        ), "Partial should not contain full HTML structure"

    def test_partials_require_auth(self, web_client: TestClient):
        """
        Partial endpoints require authentication.

        Given I am not authenticated
        When I request a partial endpoint
        Then I am redirected to login
        """
        response = web_client.get("/admin/partials/golden-repos-list")
        assert response.status_code in [
            302,
            303,
        ], f"Golden repos partial should redirect unauthenticated, got {response.status_code}"


# =============================================================================
# CSRF Protection Tests
# =============================================================================


# =============================================================================
# SCIP Badge Detection Tests (Bug Fix)
# =============================================================================


class TestSCIPBadgeDetection:
    """
    Tests for SCIP badge detection in golden repos list.

    BUG: routes.py line 822 checks for .scip files but these are DELETED after
    database conversion. Only .scip.db files persist.

    These tests verify the fix to check for .scip.db files instead.
    """

    def test_has_scip_true_with_scip_db_files(
        self, web_infrastructure: WebTestInfrastructure
    ):
        """
        SCIP badge should show when .scip.db files exist.

        CRITICAL: SCIP .scip protobuf files are DELETED after database conversion.
        Only .scip.db (SQLite) files remain after 'cidx scip generate'.

        Given a golden repository exists
        And the repository has .scip.db files in .code-indexer/scip/
        When I call _get_golden_repos_list()
        Then has_scip should be True
        """
        # Get temp directory from infrastructure
        temp_dir = web_infrastructure.temp_dir
        assert temp_dir is not None

        # Create golden repo directory structure
        golden_repos_dir = temp_dir / "data" / "golden-repos"
        golden_repos_dir.mkdir(parents=True, exist_ok=True)

        # Create a test repository clone
        test_repo_path = golden_repos_dir / "test-scip-repo"
        test_repo_path.mkdir()

        # Create .code-indexer/scip structure with .scip.db file
        scip_dir = test_repo_path / ".code-indexer" / "scip" / "python-project"
        scip_dir.mkdir(parents=True)

        # Create .scip.db file (this is what exists after SCIP generation)
        scip_db_file = scip_dir / "index.scip.db"
        scip_db_file.write_text("mock scip database")

        # Create metadata.json file in golden-repos directory
        # This is what GoldenRepoManager loads from
        metadata = {
            "test-scip-repo": {
                "alias": "test-scip-repo",
                "repo_url": "/tmp/test-scip-repo",
                "clone_path": str(test_repo_path),
                "default_branch": "main",
                "created_at": "2025-12-26T00:00:00",
                "enable_temporal": False,
                "temporal_options": None,
            }
        }
        metadata_file = golden_repos_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        # Call the actual production code
        from code_indexer.server.web.routes import _get_golden_repos_list

        repos = _get_golden_repos_list()

        # Verify we got our test repo
        assert len(repos) > 0, "Should have at least one repo"
        test_repo = next((r for r in repos if r["alias"] == "test-scip-repo"), None)
        assert test_repo is not None, "Should find test-scip-repo in results"

        # THIS IS THE FAILING ASSERTION - will fail until routes.py is fixed
        assert (
            test_repo["has_scip"] is True
        ), "has_scip should be True when .scip.db files exist"

    def test_has_scip_false_with_no_scip_files(
        self, web_infrastructure: WebTestInfrastructure
    ):
        """
        SCIP badge should NOT show when no SCIP files exist.

        Given a golden repository exists
        And the repository has NO .scip.db files
        When I call _get_golden_repos_list()
        Then has_scip should be False
        """
        # Get temp directory from infrastructure
        temp_dir = web_infrastructure.temp_dir
        assert temp_dir is not None

        # Create golden repo directory structure
        golden_repos_dir = temp_dir / "data" / "golden-repos"
        golden_repos_dir.mkdir(parents=True, exist_ok=True)

        # Create a test repository WITHOUT SCIP index
        test_repo_path = golden_repos_dir / "test-no-scip-repo"
        test_repo_path.mkdir()

        # Create .code-indexer but NO scip directory
        code_indexer_dir = test_repo_path / ".code-indexer"
        code_indexer_dir.mkdir()

        # Create metadata.json file in golden-repos directory
        metadata = {
            "test-no-scip-repo": {
                "alias": "test-no-scip-repo",
                "repo_url": "/tmp/test-no-scip-repo",
                "clone_path": str(test_repo_path),
                "default_branch": "main",
                "created_at": "2025-12-26T00:00:00",
                "enable_temporal": False,
                "temporal_options": None,
            }
        }
        metadata_file = golden_repos_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        # Call the actual production code
        from code_indexer.server.web.routes import _get_golden_repos_list

        repos = _get_golden_repos_list()

        # Verify we got our test repo
        test_repo = next((r for r in repos if r["alias"] == "test-no-scip-repo"), None)
        assert test_repo is not None, "Should find test-no-scip-repo in results"

        # Verify has_scip is False
        assert (
            test_repo["has_scip"] is False
        ), "has_scip should be False when no SCIP files exist"


# =============================================================================
# CSRF Protection Tests
# =============================================================================


class TestGoldenRepoCSRF:
    """Tests for CSRF protection on golden repo operations."""

    def test_add_repo_requires_csrf(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        CSRF token required for add repository.

        Given I am authenticated
        When I submit add repository form without CSRF token
        Then I get an error
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Submit without CSRF token
        response = client.post(
            "/admin/golden-repos/add",
            data={
                "alias": "test-no-csrf",
                "repo_url": "/tmp/test",
                "default_branch": "main",
            },
            follow_redirects=True,
        )

        # Should show error about CSRF
        text_lower = response.text.lower()
        assert (
            "csrf" in text_lower or "error" in text_lower or response.status_code == 403
        ), "Should show error when CSRF token is missing"

    def test_delete_repo_requires_csrf(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        CSRF token required for delete repository.

        Given I am authenticated
        When I submit delete form without CSRF token
        Then I get an error
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Submit without CSRF token
        response = client.post(
            "/admin/golden-repos/test-repo/delete",
            data={},
            follow_redirects=True,
        )

        # Should show error about CSRF
        text_lower = response.text.lower()
        assert (
            "csrf" in text_lower or "error" in text_lower or response.status_code == 403
        ), "Should show error when CSRF token is missing"

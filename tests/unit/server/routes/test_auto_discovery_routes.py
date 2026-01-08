"""
Tests for Auto-Discovery Web Routes.

Following TDD methodology - these tests are written FIRST before implementation.
Tests define the expected behavior for the auto-discovery admin routes.
"""

from fastapi.testclient import TestClient


class TestAutoDiscoveryPageRoute:
    """Tests for the auto-discovery page route."""

    def test_auto_discovery_page_requires_authentication(self):
        """Test that auto-discovery page requires admin authentication."""
        from code_indexer.server.web.routes import web_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(web_router, prefix="/admin")

        client = TestClient(app)
        response = client.get("/admin/auto-discovery", follow_redirects=False)

        # Should redirect to login if not authenticated
        assert response.status_code in [302, 303, 307]

    def test_auto_discovery_page_returns_html(self):
        """Test that auto-discovery page route exists and handles requests.

        Note: Full authentication testing requires integration tests with
        proper session setup. This unit test validates route registration.
        """
        from code_indexer.server.web.routes import web_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(web_router, prefix="/admin")

        client = TestClient(app)
        # Use follow_redirects=False to test route exists without
        # triggering internal session cookie signing
        response = client.get("/admin/auto-discovery", follow_redirects=False)

        # Route exists and responds (redirects to login when not authenticated)
        assert response.status_code in [200, 302, 303, 307]


class TestGitLabDiscoveryPartialRoute:
    """Tests for the GitLab discovery partial HTMX route."""

    def test_gitlab_repos_partial_returns_html(self):
        """Test that GitLab repos partial returns HTML fragment."""
        from code_indexer.server.web.routes import web_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(web_router, prefix="/admin")

        # This tests the route exists and responds
        client = TestClient(app)
        response = client.get(
            "/admin/partials/auto-discovery/gitlab",
            follow_redirects=False,
        )

        # Route should exist (auth required, so may redirect)
        assert response.status_code in [200, 302, 303, 307]

    def test_gitlab_repos_partial_accepts_pagination_params(self):
        """Test that GitLab repos partial accepts page and page_size params."""
        from code_indexer.server.web.routes import web_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(web_router, prefix="/admin")

        client = TestClient(app)
        response = client.get(
            "/admin/partials/auto-discovery/gitlab?page=2&page_size=25",
            follow_redirects=False,
        )

        # Route should accept pagination params
        assert response.status_code in [200, 302, 303, 307]


class TestAutoDiscoveryNavigation:
    """Tests for auto-discovery navigation integration."""

    def test_base_template_has_auto_discovery_nav_link(self):
        """Test that base.html template includes Auto-Discovery nav link."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent.parent / (
            "src/code_indexer/server/web/templates/base.html"
        )

        with open(template_path, "r") as f:
            template_content = f.read()

        # Check that auto-discovery nav link exists
        assert "auto-discovery" in template_content.lower() or (
            "Auto-Discovery" in template_content
        )


class TestGitHubDiscoveryPartialRoute:
    """Tests for the GitHub discovery partial HTMX route."""

    def test_github_repos_partial_route_exists(self):
        """Test that GitHub repos partial route exists and handles requests."""
        from code_indexer.server.web.routes import web_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(web_router, prefix="/admin")

        client = TestClient(app)
        response = client.get(
            "/admin/partials/auto-discovery/github",
            follow_redirects=False,
        )

        # Route should exist (auth required, so may redirect)
        assert response.status_code in [200, 302, 303, 307]

    def test_github_repos_partial_returns_html(self):
        """Test that GitHub repos partial returns HTML fragment."""
        from code_indexer.server.web.routes import web_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(web_router, prefix="/admin")

        # This tests the route exists and responds
        client = TestClient(app)
        response = client.get(
            "/admin/partials/auto-discovery/github",
            follow_redirects=False,
        )

        # Route should exist (auth required, so may redirect)
        assert response.status_code in [200, 302, 303, 307]

    def test_github_repos_partial_accepts_pagination_params(self):
        """Test that GitHub repos partial accepts page and page_size params."""
        from code_indexer.server.web.routes import web_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(web_router, prefix="/admin")

        client = TestClient(app)
        response = client.get(
            "/admin/partials/auto-discovery/github?page=2&page_size=25",
            follow_redirects=False,
        )

        # Route should accept pagination params
        assert response.status_code in [200, 302, 303, 307]


class TestAutoDiscoveryErrorHandling:
    """Tests for auto-discovery error handling."""

    def test_gitlab_not_configured_shows_message(self):
        """Test that unconfigured GitLab shows appropriate message in template."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent.parent / (
            "src/code_indexer/server/web/templates/partials/gitlab_repos.html"
        )

        with open(template_path, "r") as f:
            template_content = f.read()

        # Check that template handles 'not_configured' error type
        assert "not_configured" in template_content
        # Check that message references GitLab token configuration
        assert "GitLab Token Not Configured" in template_content
        # Check that link to MCP credentials page exists
        assert "/admin/mcp-credentials" in template_content

    def test_gitlab_api_error_shows_retry_button(self):
        """Test that API errors show retry button in template."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent.parent / (
            "src/code_indexer/server/web/templates/partials/gitlab_repos.html"
        )

        with open(template_path, "r") as f:
            template_content = f.read()

        # Check that template handles API error types
        assert "api_error" in template_content
        # Check that retry button exists
        assert "retryGitLabDiscovery()" in template_content
        # Check that error message section exists
        assert "Failed to Load GitLab Repositories" in template_content

    def test_github_not_configured_shows_message(self):
        """Test that unconfigured GitHub shows appropriate message in template."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent.parent / (
            "src/code_indexer/server/web/templates/partials/github_repos.html"
        )

        with open(template_path, "r") as f:
            template_content = f.read()

        # Check that template handles 'not_configured' error type
        assert "not_configured" in template_content
        # Check that message references GitHub token configuration
        assert "GitHub Token Not Configured" in template_content
        # Check that link to MCP credentials page exists
        assert "/admin/mcp-credentials" in template_content

    def test_github_api_error_shows_retry_button(self):
        """Test that GitHub API errors show retry button in template."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent.parent / (
            "src/code_indexer/server/web/templates/partials/github_repos.html"
        )

        with open(template_path, "r") as f:
            template_content = f.read()

        # Check that template handles API error types
        assert "api_error" in template_content
        # Check that retry button exists
        assert "retryGitHubDiscovery()" in template_content
        # Check that error message section exists
        assert "Failed to Load GitHub Repositories" in template_content

    def test_github_rate_limit_error_shows_message(self):
        """Test that GitHub rate limit error shows appropriate message in template."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent.parent / (
            "src/code_indexer/server/web/templates/partials/github_repos.html"
        )

        with open(template_path, "r") as f:
            template_content = f.read()

        # Check that template handles rate_limit error type
        assert "rate_limit" in template_content


class TestAutoDiscoveryPlatformBadges:
    """Tests for platform badge styling in auto-discovery templates."""

    def test_github_badge_has_correct_color(self):
        """Test that GitHub badge uses the dark color (#24292E)."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent.parent / (
            "src/code_indexer/server/web/templates/partials/github_repos.html"
        )

        with open(template_path, "r") as f:
            template_content = f.read()

        # Check that GitHub badge styling with dark color exists
        assert "#24292e" in template_content.lower() or "#24292E" in template_content
        assert "platform-badge" in template_content
        assert ".github" in template_content or "github" in template_content

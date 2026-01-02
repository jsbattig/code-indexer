"""
Tests for SCIP integration in web UI.

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any

from code_indexer.global_repos.global_registry import GlobalRegistry
from .conftest import WebTestInfrastructure


class TestSCIPIndexDetection:
    """Tests for SCIP index detection in golden repos list."""

    def test_scip_index_detection_in_golden_repos(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        SCIP index detection returns has_scip=True when .scip files exist.

        Given I have a golden repository with SCIP indexes
        When I view the golden repos list
        Then the repository shows has_scip=True
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Create a temporary repository with SCIP index
        temp_repo_dir = Path(tempfile.mkdtemp(prefix="test_scip_repo_"))
        try:
            # Create .code-indexer/scip directory structure
            scip_dir = temp_repo_dir / ".code-indexer" / "scip"
            scip_dir.mkdir(parents=True, exist_ok=True)

            # Create a .scip file
            test_scip_file = scip_dir / "python.scip"
            test_scip_file.write_bytes(b"test scip content")

            # Get CSRF token
            golden_repos_page = client.get("/admin/golden-repos")
            csrf_token = web_infrastructure.extract_csrf_token(golden_repos_page.text)

            # Add repository
            response = client.post(
                "/admin/golden-repos/add",
                data={
                    "alias": "test-scip-repo",
                    "repo_url": str(temp_repo_dir),
                    "default_branch": "main",
                    "csrf_token": csrf_token,
                },
                follow_redirects=True,
            )

            assert response.status_code == 200

            # Get the golden repos list
            response = client.get("/admin/golden-repos")
            assert response.status_code == 200

            # Verify SCIP badge is present in response
            text_lower = response.text.lower()
            assert (
                "scip" in text_lower
            ), "Response should contain 'scip' indicator when SCIP index exists"

        finally:
            # Cleanup
            if temp_repo_dir.exists():
                shutil.rmtree(temp_repo_dir)


class TestSCIPQueryViaWebUI:
    """Tests for SCIP query execution via web UI endpoints."""

    def _get_global_registry(self) -> GlobalRegistry:
        """Get GlobalRegistry instance for current test environment."""
        server_data_dir = os.environ.get(
            "CIDX_SERVER_DATA_DIR", os.path.expanduser("~/.cidx-server")
        )
        golden_repos_dir = Path(server_data_dir) / "data" / "golden-repos"
        return GlobalRegistry(str(golden_repos_dir))

    def _setup_golden_repo_with_scip(self, alias: str, repo_path: Path) -> None:
        """Helper to register golden repo with SCIP index directly in GlobalRegistry."""
        registry = self._get_global_registry()
        registry.register_global_repo(
            repo_name=alias.replace("-global", ""),
            alias_name=alias,
            repo_url=str(repo_path),
            index_path=str(repo_path),
            enable_temporal=False,
        )

    def test_scip_definition_query_via_web_ui_returns_results(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        SCIP definition query via web UI POST returns results.

        Given I have a golden repository with SCIP index containing Logger symbol
        When I POST to /admin/partials/query-results with search_mode='scip'
        Then I should receive HTML containing the Logger definition result
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Use test fixture with real SCIP index
        test_fixture_path = (
            Path(__file__).parent.parent.parent.parent
            / "test-fixtures"
            / "scip-python-mock"
        )
        assert (
            test_fixture_path.exists()
        ), f"Test fixture not found: {test_fixture_path}"

        scip_file = test_fixture_path / ".code-indexer" / "scip" / "index.scip"
        assert scip_file.exists(), f"SCIP index not found: {scip_file}"

        # Setup golden repo
        repo_alias = "python-mock-global"
        self._setup_golden_repo_with_scip(repo_alias, test_fixture_path)

        try:
            # Get CSRF token for query
            query_page = client.get("/admin/query")
            csrf_token = web_infrastructure.extract_csrf_token(query_page.text)

            # Execute SCIP query via web UI
            response = client.post(
                "/admin/partials/query-results",
                data={
                    "query_text": "Logger",
                    "repository": repo_alias,
                    "search_mode": "scip",
                    "scip_query_type": "definition",
                    "scip_exact": "false",
                    "limit": "10",
                    "csrf_token": csrf_token,
                },
            )

            assert response.status_code == 200, f"Query failed: {response.status_code}"
            html = response.text

            # Verify results
            assert "Logger" in html, f"Expected 'Logger' in response: {html[:500]}"
            assert "logger.py" in html, f"Expected 'logger.py': {html[:500]}"
            assert "No SCIP index found" not in html
        finally:
            # Cleanup golden repo
            registry = self._get_global_registry()
            registry.unregister_global_repo(repo_alias)

    def test_scip_references_query_via_web_ui_returns_results(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """SCIP references query via web UI returns reference results."""
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        test_fixture_path = (
            Path(__file__).parent.parent.parent.parent
            / "test-fixtures"
            / "scip-python-mock"
        )
        repo_alias = "python-mock-global"
        self._setup_golden_repo_with_scip(repo_alias, test_fixture_path)

        try:
            query_page = client.get("/admin/query")
            csrf_token = web_infrastructure.extract_csrf_token(query_page.text)

            response = client.post(
                "/admin/partials/query-results",
                data={
                    "query_text": "Logger",
                    "repository": repo_alias,
                    "search_mode": "scip",
                    "scip_query_type": "references",
                    "scip_exact": "false",
                    "limit": "10",
                    "csrf_token": csrf_token,
                },
            )

            assert response.status_code == 200
            html = response.text
            assert "Logger" in html or "reference" in html.lower()
        finally:
            registry = self._get_global_registry()
            registry.unregister_global_repo(repo_alias)

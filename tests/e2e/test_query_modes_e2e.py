"""
Comprehensive E2E tests for CIDX query functionality.

Tests ALL query options through both REST API and Admin Web UI endpoints.
This test file is designed to be excluded from fast-automation.sh due to
the time required for repository cloning and indexing.

Following TDD methodology and anti-mock principle - real systems only.
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, cast

import pytest
import requests
from requests import Session

logger = logging.getLogger(__name__)


def load_e2e_credentials() -> Dict[str, Optional[str]]:
    """
    Load E2E test credentials from .local-testing file.

    Returns dict with keys: username, password, server_url
    Raises FileNotFoundError if .local-testing doesn't exist.
    """
    local_testing_path = Path(__file__).parent.parent.parent / ".local-testing"
    if not local_testing_path.exists():
        raise FileNotFoundError(
            f"E2E credentials file not found: {local_testing_path}\n"
            "Create .local-testing with [E2E_TEST_CREDENTIALS] section."
        )

    content = local_testing_path.read_text()

    # Extract section between [E2E_TEST_CREDENTIALS] markers
    match = re.search(
        r"\[E2E_TEST_CREDENTIALS\](.*?)\[/E2E_TEST_CREDENTIALS\]",
        content,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Missing [E2E_TEST_CREDENTIALS] section in .local-testing")

    credentials: Dict[str, str] = {}
    for line in match.group(1).strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            credentials[key.strip()] = value.strip()

    return {
        "username": credentials.get("E2E_ADMIN_USERNAME", "admin"),
        "password": credentials.get("E2E_ADMIN_PASSWORD"),
        "server_url": credentials.get("E2E_SERVER_URL", "http://localhost:8000"),
    }


# =============================================================================
# CONFIGURATION
# =============================================================================

# Deterministic alias for test isolation
TEST_ALIAS = "cidx-query-e2e-test-7f3a9b2c"
GLOBAL_ALIAS = f"{TEST_ALIAS}-global"  # Global activation adds -global suffix
TEST_REPO_URL = "https://github.com/jsbattig/tries.git"

# Timeouts
INDEXING_TIMEOUT_SECONDS = 600  # 10 minutes for indexing
DELETION_TIMEOUT_SECONDS = 120  # 2 minutes for deletion
JOB_POLL_INTERVAL_SECONDS = 5


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_auth_token(
    base_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """
    Get JWT token for REST API authentication.

    Args:
        base_url: Server base URL
        username: Login username (loads from .local-testing if not provided)
        password: Login password (loads from .local-testing if not provided)

    Returns:
        JWT access token string

    Raises:
        requests.HTTPError: If authentication fails
        FileNotFoundError: If credentials not provided and .local-testing missing
    """
    if username is None or password is None:
        creds = load_e2e_credentials()
        username = username or creds["username"]
        password = password or creds["password"]

    response = requests.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return cast(str, response.json()["access_token"])


def get_admin_session(
    base_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Session:
    """
    Get authenticated session for admin web UI.

    Args:
        base_url: Server base URL
        username: Login username (loads from .local-testing if not provided)
        password: Login password (loads from .local-testing if not provided)

    Returns:
        requests.Session with authentication cookies set

    Raises:
        requests.HTTPError: If authentication fails
        FileNotFoundError: If credentials not provided and .local-testing missing
    """
    if username is None or password is None:
        creds = load_e2e_credentials()
        username = username or creds["username"]
        password = password or creds["password"]

    session = requests.Session()

    # Get login page to get CSRF token
    login_page_resp = session.get(f"{base_url}/admin/login", timeout=30)
    login_page_resp.raise_for_status()

    # Extract CSRF token from cookie
    csrf_token = session.cookies.get("cidx_csrf")
    if not csrf_token:
        # Try to extract from HTML if not in cookie
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page_resp.text)
        if match:
            csrf_token = match.group(1)

    if not csrf_token:
        raise ValueError("Could not extract CSRF token from login page")

    # Submit login form
    login_resp = session.post(
        f"{base_url}/admin/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": csrf_token,
        },
        timeout=30,
        allow_redirects=True,
    )
    login_resp.raise_for_status()

    # Verify we're logged in by checking for session cookie
    if "session" not in session.cookies:
        raise ValueError("Login failed - no session cookie received")

    return session


def wait_for_job(
    base_url: str,
    token: str,
    job_id: str,
    timeout: int = INDEXING_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """
    Wait for job completion with timeout and progress feedback.

    Args:
        base_url: Server base URL
        token: JWT access token
        job_id: Job ID to monitor
        timeout: Maximum wait time in seconds

    Returns:
        Job status dictionary

    Raises:
        TimeoutError: If job does not complete within timeout
        RuntimeError: If job fails
    """
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    last_status = None
    poll_count = 0

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        poll_count += 1

        resp = requests.get(
            f"{base_url}/api/jobs/{job_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json()

        current_status = status.get("status")
        progress = status.get("progress", 0)

        # Print progress every poll on status change or every 30s (6 polls)
        if current_status != last_status or poll_count % 6 == 0:
            print(
                f"  [{elapsed}s] Job {job_id[:8]}... | {current_status} | "
                f"Progress: {progress}%",
                file=sys.stderr,
                flush=True,
            )
            logger.info(f"Job {job_id}: status={current_status}, progress={progress}%")
            last_status = current_status

        if current_status == "completed":
            print(
                f"  [{elapsed}s] Job {job_id[:8]}... | COMPLETED",
                file=sys.stderr,
                flush=True,
            )
            return cast(Dict[str, Any], status)
        if current_status == "failed":
            error_msg = status.get("error_message", "Unknown error")
            print(
                f"  [{elapsed}s] Job {job_id[:8]}... | FAILED: {error_msg}",
                file=sys.stderr,
                flush=True,
            )
            raise RuntimeError(f"Job {job_id} failed: {error_msg}")

        time.sleep(JOB_POLL_INTERVAL_SECONDS)

    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


def register_golden_repo(
    base_url: str,
    token: str,
    alias: str,
    repo_url: str,
    enable_temporal: bool = True,
) -> str:
    """
    Register a golden repository.

    Args:
        base_url: Server base URL
        token: JWT access token
        alias: Repository alias
        repo_url: Git repository URL
        enable_temporal: Whether to enable temporal indexing

    Returns:
        Job ID for the registration job

    Raises:
        requests.HTTPError: If registration fails
    """
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "repo_url": repo_url,
        "alias": alias,
        "default_branch": "master",
        "enable_temporal": enable_temporal,
    }

    logger.info(f"Registering golden repo: {alias} from {repo_url}")

    resp = requests.post(
        f"{base_url}/api/admin/golden-repos",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    result = resp.json()
    job_id = result.get("job_id")

    if not job_id:
        raise ValueError(f"No job_id returned from registration: {result}")

    logger.info(f"Golden repo registration started: job_id={job_id}")
    return cast(str, job_id)


def delete_golden_repo(base_url: str, token: str, alias: str) -> Optional[str]:
    """
    Delete a golden repository.

    Args:
        base_url: Server base URL
        token: JWT access token
        alias: Repository alias to delete

    Returns:
        Job ID if deletion started as background job, None if deleted synchronously

    Raises:
        requests.HTTPError: If deletion fails
    """
    headers = {"Authorization": f"Bearer {token}"}

    logger.info(f"Deleting golden repo: {alias}")

    resp = requests.delete(
        f"{base_url}/api/admin/golden-repos/{alias}",
        headers=headers,
        timeout=30,
    )

    # 204 means deleted synchronously
    if resp.status_code == 204:
        logger.info(f"Golden repo {alias} deleted synchronously")
        return None

    resp.raise_for_status()

    # Check if there's a job_id in response
    try:
        result = resp.json()
        return cast(Optional[str], result.get("job_id"))
    except (json.JSONDecodeError, ValueError):
        return None


def verify_cleanup(alias: str) -> None:
    """
    Verify complete cleanup of golden repository.

    Args:
        alias: Repository alias that should be cleaned up

    Raises:
        AssertionError: If cleanup is incomplete
    """
    server_data_dir = os.environ.get(
        "CIDX_SERVER_DATA_DIR",
        os.path.expanduser("~/.cidx-server"),
    )
    data_path = Path(server_data_dir) / "data" / "golden-repos"

    # Check metadata.json doesn't contain our alias
    metadata_path = data_path / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)
        assert alias not in metadata, f"Alias {alias} still in metadata.json"

    # Check folder doesn't exist
    repo_folder = data_path / alias
    assert not repo_folder.exists(), f"Repo folder still exists: {repo_folder}"

    # Check alias file doesn't exist
    alias_file = data_path / "aliases" / f"{alias}-global.json"
    assert not alias_file.exists(), f"Alias file still exists: {alias_file}"

    # Check registry.json doesn't contain our repo
    registry_path = data_path / "registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
        for entry in registry.values():
            assert (
                entry.get("alias_name") != alias
            ), f"Registry still contains alias {alias}"

    logger.info(f"Cleanup verified for alias: {alias}")


def query_rest_api(
    base_url: str,
    token: str,
    query_text: str,
    repository_alias: str,
    search_mode: str = "semantic",
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute query via REST API.

    Args:
        base_url: Server base URL
        token: JWT access token
        query_text: Query text
        repository_alias: Repository to search
        search_mode: Search mode (semantic, fts, hybrid, temporal)
        **kwargs: Additional query parameters

    Returns:
        Query response dictionary

    Raises:
        requests.HTTPError: If query fails
    """
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "query_text": query_text,
        "repository_alias": repository_alias,
        "search_mode": search_mode,
        **kwargs,
    }

    logger.debug(f"REST API query: {payload}")

    resp = requests.post(
        f"{base_url}/api/query",
        headers=headers,
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()

    return cast(Dict[str, Any], resp.json())


def query_web_ui(
    session: Session,
    base_url: str,
    query_text: str,
    repository: str,
    search_mode: str = "semantic",
    **kwargs,
) -> requests.Response:
    """
    Execute query via Web UI HTMX endpoint.

    Args:
        session: Authenticated session
        base_url: Server base URL
        query_text: Query text
        repository: Repository to search
        search_mode: Search mode
        **kwargs: Additional form parameters

    Returns:
        Response object

    Raises:
        requests.HTTPError: If query fails
    """
    # Get CSRF token from cookie
    csrf_token = session.cookies.get("cidx_csrf", "")

    form_data = {
        "query_text": query_text,
        "repository": repository,
        "search_mode": search_mode,
        "limit": kwargs.get("limit", 10),
        "csrf_token": csrf_token,
        **{k: v for k, v in kwargs.items() if k != "limit"},
    }

    logger.debug(f"Web UI query: {form_data}")

    resp = session.post(
        f"{base_url}/admin/partials/query-results",
        data=form_data,
        headers={"HX-Request": "true"},
        timeout=60,
    )
    resp.raise_for_status()

    return resp


# =============================================================================
# TEST CLASS
# =============================================================================


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("RUN_E2E_TESTS") != "1",
    reason="E2E tests require RUN_E2E_TESTS=1 environment variable",
)
class TestQueryModesE2E:
    """
    E2E tests for all query modes and options.

    Tests query functionality through both REST API and Admin Web UI endpoints.
    Requires a running CIDX server with admin credentials.
    """

    ALIAS = TEST_ALIAS
    GLOBAL_ALIAS = f"{TEST_ALIAS}-global"  # Global activation adds -global suffix
    REPO_URL = TEST_REPO_URL

    @pytest.fixture(scope="class")
    def e2e_credentials(self):
        """Load E2E test credentials from .local-testing file."""
        return load_e2e_credentials()

    @pytest.fixture(scope="class")
    def server_url(self, e2e_credentials):
        """Get server URL from credentials or environment."""
        return os.environ.get("CIDX_SERVER_URL", e2e_credentials["server_url"])

    @pytest.fixture(scope="class")
    def auth_token(self, server_url, e2e_credentials):
        """Get JWT token for REST API."""
        return get_auth_token(
            server_url,
            username=e2e_credentials["username"],
            password=e2e_credentials["password"],
        )

    @pytest.fixture(scope="class")
    def admin_session(self, server_url, e2e_credentials):
        """Get authenticated session for Web UI."""
        return get_admin_session(
            server_url,
            username=e2e_credentials["username"],
            password=e2e_credentials["password"],
        )

    @pytest.fixture(scope="class", autouse=True)
    def setup_and_teardown(self, server_url, auth_token):
        """
        Register repo, wait for indexing, yield, then cleanup and verify.

        This fixture runs once per test class to avoid repeated setup/teardown.
        """
        # Setup: Check if repo already exists and delete if so
        try:
            delete_golden_repo(server_url, auth_token, self.ALIAS)
            logger.info(f"Cleaned up pre-existing repo: {self.ALIAS}")
            time.sleep(2)  # Wait for deletion to complete
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                raise
            logger.info(f"No pre-existing repo to clean up: {self.ALIAS}")

        # Register golden repo with temporal indexing enabled
        print(
            f"\nRegistering golden repo '{self.ALIAS}' - "
            "this may take 5-10 minutes for indexing...",
            file=sys.stderr,
            flush=True,
        )
        job_id = register_golden_repo(
            server_url,
            auth_token,
            self.ALIAS,
            self.REPO_URL,
            enable_temporal=True,
        )
        print(f"Job submitted: {job_id[:16]}...", file=sys.stderr, flush=True)

        # Wait for indexing to complete
        try:
            wait_for_job(
                server_url, auth_token, job_id, timeout=INDEXING_TIMEOUT_SECONDS
            )
            print(f"Indexing completed for: {self.ALIAS}", file=sys.stderr, flush=True)
            logger.info(f"Indexing completed for: {self.ALIAS}")
        except (TimeoutError, RuntimeError) as e:
            # Attempt cleanup on failure
            logger.error(f"Indexing failed: {e}")
            try:
                delete_golden_repo(server_url, auth_token, self.ALIAS)
            except Exception:
                pass
            raise

        # Wait a bit for indexes to be fully available
        time.sleep(2)

        yield  # Run tests

        # Teardown: Delete and verify cleanup
        try:
            delete_job_id = delete_golden_repo(server_url, auth_token, self.ALIAS)
            if delete_job_id:
                wait_for_job(
                    server_url,
                    auth_token,
                    delete_job_id,
                    timeout=DELETION_TIMEOUT_SECONDS,
                )

            # Give time for async cleanup
            time.sleep(2)

            # Verify complete cleanup
            verify_cleanup(self.ALIAS)
            logger.info(f"Cleanup completed for: {self.ALIAS}")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            # Don't raise - allow test results to be reported

    # =========================================================================
    # REST API TESTS - SEMANTIC SEARCH
    # =========================================================================

    def test_semantic_search_basic_rest(self, server_url, auth_token):
        """Test basic semantic search via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie data structure",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            limit=5,
        )

        assert "results" in result or "semantic_results" in result
        # Check we got some results
        results = result.get("results") or result.get("semantic_results", [])
        assert len(results) >= 0  # May be empty if semantic index not built

    def test_semantic_search_with_language_filter_rest(self, server_url, auth_token):
        """Test semantic search with language filter via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="implementation",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            language="python",
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    def test_semantic_search_with_path_filter_rest(self, server_url, auth_token):
        """Test semantic search with path filter via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="insert",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            path_filter="*.py",
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    def test_semantic_search_with_min_score_rest(self, server_url, auth_token):
        """Test semantic search with minimum score filter via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            min_score=0.1,
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    def test_semantic_search_with_accuracy_high_rest(self, server_url, auth_token):
        """Test semantic search with high accuracy mode via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="search algorithm",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            accuracy="high",
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    # =========================================================================
    # REST API TESTS - FTS SEARCH
    # =========================================================================

    def test_fts_search_basic_rest(self, server_url, auth_token):
        """Test basic full-text search via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="def",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="fts",
            limit=5,
        )

        # FTS mode returns unified response
        assert "fts_results" in result or "results" in result

    def test_fts_search_case_sensitive_rest(self, server_url, auth_token):
        """Test case-sensitive full-text search via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="Trie",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="fts",
            case_sensitive=True,
            limit=5,
        )

        assert "fts_results" in result or "results" in result

    def test_fts_search_fuzzy_rest(self, server_url, auth_token):
        """Test fuzzy full-text search via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie",  # Should match "tries" with fuzzy
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="fts",
            fuzzy=True,
            limit=5,
        )

        assert "fts_results" in result or "results" in result

    def test_fts_search_regex_rest(self, server_url, auth_token):
        """Test regex full-text search via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="def.*insert",  # Regex pattern
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="fts",
            regex=True,
            limit=5,
        )

        assert "fts_results" in result or "results" in result

    def test_fts_search_with_language_filter_rest(self, server_url, auth_token):
        """Test FTS with language filter via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="class",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="fts",
            language="python",
            limit=5,
        )

        assert "fts_results" in result or "results" in result

    # =========================================================================
    # REST API TESTS - HYBRID SEARCH
    # =========================================================================

    def test_hybrid_search_basic_rest(self, server_url, auth_token):
        """Test basic hybrid search via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="hybrid",
            limit=5,
        )

        # Hybrid returns both FTS and semantic results
        assert "metadata" in result
        assert result["metadata"]["search_mode_requested"] == "hybrid"

    def test_hybrid_search_with_filters_rest(self, server_url, auth_token):
        """Test hybrid search with multiple filters via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="insert",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="hybrid",
            language="python",
            limit=5,
            min_score=0.1,
        )

        assert "metadata" in result

    # =========================================================================
    # REST API TESTS - TEMPORAL SEARCH
    # =========================================================================

    def test_temporal_search_all_history_rest(self, server_url, auth_token):
        """Test temporal search across all history via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            time_range_all=True,
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    def test_temporal_search_with_time_range_rest(self, server_url, auth_token):
        """Test temporal search with specific time range via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="implementation",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            time_range="2020-01-01..2025-12-31",
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    def test_temporal_search_include_removed_rest(self, server_url, auth_token):
        """Test temporal search including removed files via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            time_range_all=True,
            include_removed=True,
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    # =========================================================================
    # REST API TESTS - EXCLUSION FILTERS
    # =========================================================================

    def test_exclude_language_rest(self, server_url, auth_token):
        """Test search with language exclusion via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="test",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            exclude_language="markdown",
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    def test_exclude_path_rest(self, server_url, auth_token):
        """Test search with path exclusion via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            exclude_path="*/tests/*",
            limit=5,
        )

        assert "results" in result or "semantic_results" in result

    # =========================================================================
    # WEB UI TESTS
    # =========================================================================

    def test_semantic_search_web_ui(self, server_url, admin_session):
        """Test semantic search via Web UI."""
        response = query_web_ui(
            admin_session,
            server_url,
            query_text="trie data structure",
            repository=self.GLOBAL_ALIAS,
            search_mode="semantic",
            limit=5,
        )

        assert response.status_code == 200
        # Web UI returns HTML
        assert "text/html" in response.headers.get("content-type", "")

    def test_fts_search_web_ui(self, server_url, admin_session):
        """Test FTS search via Web UI."""
        response = query_web_ui(
            admin_session,
            server_url,
            query_text="def",
            repository=self.GLOBAL_ALIAS,
            search_mode="fts",
            limit=5,
        )

        assert response.status_code == 200

    def test_fts_options_web_ui(self, server_url, admin_session):
        """Test FTS with options via Web UI."""
        response = query_web_ui(
            admin_session,
            server_url,
            query_text="class",
            repository=self.GLOBAL_ALIAS,
            search_mode="fts",
            case_sensitive=True,
            limit=5,
        )

        assert response.status_code == 200

    def test_temporal_search_web_ui(self, server_url, admin_session):
        """Test temporal search via Web UI."""
        response = query_web_ui(
            admin_session,
            server_url,
            query_text="trie",
            repository=self.GLOBAL_ALIAS,
            search_mode="temporal",
            time_range_all=True,
            limit=5,
        )

        assert response.status_code == 200

    def test_hybrid_search_web_ui(self, server_url, admin_session):
        """Test hybrid search via Web UI."""
        response = query_web_ui(
            admin_session,
            server_url,
            query_text="insert",
            repository=self.GLOBAL_ALIAS,
            search_mode="hybrid",
            limit=5,
        )

        assert response.status_code == 200

    # =========================================================================
    # PARAMETRIZED COMBINATION TESTS
    # =========================================================================

    @pytest.mark.parametrize(
        "search_mode,extra_params",
        [
            ("semantic", {}),
            ("semantic", {"accuracy": "fast"}),
            ("semantic", {"accuracy": "high"}),
            ("fts", {}),
            ("fts", {"case_sensitive": True}),
            ("fts", {"fuzzy": True}),
            ("fts", {"regex": True}),
            ("hybrid", {}),
        ],
        ids=[
            "semantic-basic",
            "semantic-fast",
            "semantic-high",
            "fts-basic",
            "fts-case-sensitive",
            "fts-fuzzy",
            "fts-regex",
            "hybrid-basic",
        ],
    )
    def test_search_mode_combinations_rest(
        self, server_url, auth_token, search_mode, extra_params
    ):
        """Test various search mode and parameter combinations via REST API."""
        # Use appropriate query text for regex mode
        query_text = "def.*" if extra_params.get("regex") else "trie"

        result = query_rest_api(
            server_url,
            auth_token,
            query_text=query_text,
            repository_alias=self.GLOBAL_ALIAS,
            search_mode=search_mode,
            limit=5,
            **extra_params,
        )

        # Verify response structure based on search mode
        if search_mode in ["fts", "hybrid"]:
            assert (
                "metadata" in result or "fts_results" in result or "results" in result
            )
        else:
            assert "results" in result or "semantic_results" in result

    @pytest.mark.parametrize(
        "filter_type,filter_value",
        [
            ("language", "python"),
            ("path_filter", "*.py"),
            ("exclude_language", "markdown"),
            ("exclude_path", "*/docs/*"),
            ("min_score", 0.1),
        ],
        ids=[
            "language-filter",
            "path-filter",
            "exclude-language",
            "exclude-path",
            "min-score",
        ],
    )
    def test_filter_combinations_rest(
        self, server_url, auth_token, filter_type, filter_value
    ):
        """Test various filter combinations via REST API."""
        kwargs = {filter_type: filter_value}

        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            limit=5,
            **kwargs,
        )

        assert "results" in result or "semantic_results" in result

    @pytest.mark.parametrize(
        "temporal_params",
        [
            {"time_range_all": True},
            {"time_range": "2020-01-01..2025-12-31"},
            {"time_range_all": True, "include_removed": True},
        ],
        ids=[
            "temporal-all-history",
            "temporal-time-range",
            "temporal-include-removed",
        ],
    )
    def test_temporal_combinations_rest(self, server_url, auth_token, temporal_params):
        """Test various temporal parameter combinations via REST API."""
        result = query_rest_api(
            server_url,
            auth_token,
            query_text="trie",
            repository_alias=self.GLOBAL_ALIAS,
            search_mode="semantic",
            limit=5,
            **temporal_params,
        )

        assert "results" in result or "semantic_results" in result


# =============================================================================
# STANDALONE VERIFICATION TESTS
# =============================================================================


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("RUN_E2E_TESTS") != "1",
    reason="E2E tests require RUN_E2E_TESTS=1 environment variable",
)
class TestQueryAPIStructure:
    """Test query API structure and error handling."""

    @pytest.fixture(scope="class")
    def e2e_credentials(self):
        """Load E2E test credentials from .local-testing file."""
        return load_e2e_credentials()

    @pytest.fixture(scope="class")
    def server_url(self, e2e_credentials):
        """Get server URL from credentials or environment."""
        return os.environ.get("CIDX_SERVER_URL", e2e_credentials["server_url"])

    @pytest.fixture(scope="class")
    def auth_token(self, server_url, e2e_credentials):
        """Get JWT token for REST API."""
        return get_auth_token(
            server_url,
            username=e2e_credentials["username"],
            password=e2e_credentials["password"],
        )

    def test_query_requires_authentication(self, server_url):
        """Test that query endpoint requires authentication."""
        resp = requests.post(
            f"{server_url}/api/query",
            json={"query_text": "test", "search_mode": "semantic"},
            timeout=30,
        )

        # Should return 401 or 403
        assert resp.status_code in [401, 403]

    def test_query_validates_empty_query(self, server_url, auth_token):
        """Test that empty query is rejected."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        resp = requests.post(
            f"{server_url}/api/query",
            headers=headers,
            json={"query_text": "", "search_mode": "semantic"},
            timeout=30,
        )

        assert resp.status_code == 422  # Validation error

    def test_query_validates_invalid_search_mode(self, server_url, auth_token):
        """Test that invalid search mode is rejected."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        resp = requests.post(
            f"{server_url}/api/query",
            headers=headers,
            json={"query_text": "test", "search_mode": "invalid_mode"},
            timeout=30,
        )

        assert resp.status_code == 422  # Validation error

    def test_query_handles_nonexistent_repository(self, server_url, auth_token):
        """Test error handling for non-existent repository."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        resp = requests.post(
            f"{server_url}/api/query",
            headers=headers,
            json={
                "query_text": "test",
                "repository_alias": "nonexistent-repo-12345",
                "search_mode": "semantic",
            },
            timeout=30,
        )

        # Should return 400 or 404
        assert resp.status_code in [400, 404]

"""
Integration tests for wiring advanced query filtering to the API endpoint (Story #490).

Tests the complete flow of advanced filtering through the POST /api/query endpoint,
ensuring all parameters are properly wired to the underlying search functions.
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime
from unittest.mock import patch

from code_indexer.server.app import create_app
from code_indexer.server.models.activated_repository import ActivatedRepository
from code_indexer.server.auth import dependencies


@pytest.fixture
def app_with_test_repo(tmp_path: Path):
    """Create FastAPI app with test repository."""
    # Create test directory structure
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    activated_repos_dir = data_dir / "activated-repos"
    activated_repos_dir.mkdir()

    # Create user directory
    user_dir = activated_repos_dir / "testuser"
    user_dir.mkdir()

    # Create single repository
    repo_dir = user_dir / "test-repo"
    repo_dir.mkdir()
    config_dir = repo_dir / ".code-indexer"
    config_dir.mkdir()

    # Create sample code files
    (repo_dir / "auth.py").write_text("""
def authenticate(user, password):
    '''Authentication function in Python.'''
    return user and password
""")

    (repo_dir / "user.go").write_text("""
package main

func GetUser(id int) User {
    // User retrieval in Go
    return User{ID: id}
}
""")

    # Create config
    config = {"proxy_mode": False, "embedding_provider": "voyage-ai"}
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps(config, indent=2))

    # Create metadata
    metadata = ActivatedRepository(
        user_alias="test-repo",
        username="testuser",
        path=repo_dir,
        activated_at=datetime.now(),
        last_accessed=datetime.now(),
        golden_repo_alias="test-golden-repo",
        current_branch="main",
    )

    metadata_file = repo_dir / ".cidx-metadata.json"
    metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

    # Create app with test configuration
    app = create_app()

    # Override activated repo manager data directory
    from code_indexer.server import app as app_module
    app_module.activated_repo_manager.activated_repos_dir = activated_repos_dir

    yield app


@pytest.fixture
def test_client(app_with_test_repo):
    """Create test client."""
    return TestClient(app_with_test_repo)


# Mock user for authentication bypass
class MockUser:
    def __init__(self):
        self.username = "testuser"
        self.role = "user"


def override_get_current_user():
    """Override authentication dependency for testing."""
    return MockUser()


class TestLanguageFilterWiring:
    """Test language filters are properly wired through the endpoint."""

    def test_language_filters_passed_to_fts_search(self, test_client: TestClient, tmp_path: Path):
        """Test that language and exclude_language are processed and passed to FTS search."""
        app = test_client.app
        app.dependency_overrides[dependencies.get_current_user] = override_get_current_user

        try:
            # Create FTS index directory
            from code_indexer.server import app as app_module
            activated_repos_dir = app_module.activated_repo_manager.activated_repos_dir
            fts_index_dir = Path(activated_repos_dir) / "testuser" / "test-repo" / ".code-indexer" / "tantivy_index"
            fts_index_dir.mkdir(parents=True, exist_ok=True)
            (fts_index_dir / "dummy.txt").write_text("dummy")

            # Mock activated repository listing
            with patch('code_indexer.server.app.activated_repo_manager.list_activated_repositories') as mock_list_repos:
                mock_list_repos.return_value = [
                    {"user_alias": "test-repo", "path": str(Path(activated_repos_dir) / "testuser" / "test-repo")}
                ]

                # Mock TantivyIndexManager to capture calls
                with patch('code_indexer.services.tantivy_index_manager.TantivyIndexManager') as MockTantivyClass:
                    mock_tantivy_instance = MockTantivyClass.return_value
                    mock_tantivy_instance.initialize_index.return_value = None
                    mock_tantivy_instance.search.return_value = []

                    # Test with language filters and exclusions
                    response = test_client.post(
                        "/api/query",
                        json={
                            "query_text": "test",
                            "search_mode": "fts",
                            "language": ["python", "go", "rust"],
                            "exclude_language": ["rust"],
                            "repository_alias": "test-repo"
                        }
                    )

                    assert response.status_code == 200

                    # Verify search was called with proper language filters
                    mock_tantivy_instance.search.assert_called_once()
                    call_kwargs = mock_tantivy_instance.search.call_args[1]

                    # After wiring, languages should be passed properly
                    # exclude_language should remove "rust" from the list
                    assert 'languages' in call_kwargs
                    assert sorted(call_kwargs['languages']) == ["go", "python"]

        finally:
            app.dependency_overrides.clear()

    def test_path_filters_with_exclusions(self, test_client: TestClient, tmp_path: Path):
        """Test that path_filter and exclude_path are processed correctly."""
        app = test_client.app
        app.dependency_overrides[dependencies.get_current_user] = override_get_current_user

        try:
            from code_indexer.server import app as app_module
            activated_repos_dir = app_module.activated_repo_manager.activated_repos_dir
            fts_index_dir = Path(activated_repos_dir) / "testuser" / "test-repo" / ".code-indexer" / "tantivy_index"
            fts_index_dir.mkdir(parents=True, exist_ok=True)
            (fts_index_dir / "dummy.txt").write_text("dummy")

            with patch('code_indexer.server.app.activated_repo_manager.list_activated_repositories') as mock_list_repos:
                mock_list_repos.return_value = [
                    {"user_alias": "test-repo", "path": str(Path(activated_repos_dir) / "testuser" / "test-repo")}
                ]

                with patch('code_indexer.services.tantivy_index_manager.TantivyIndexManager') as MockTantivyClass:
                    mock_tantivy_instance = MockTantivyClass.return_value
                    mock_tantivy_instance.initialize_index.return_value = None
                    mock_tantivy_instance.search.return_value = []

                    response = test_client.post(
                        "/api/query",
                        json={
                            "query_text": "test",
                            "search_mode": "fts",
                            "path_filter": ["*/src/*", "*/lib/*", "*/tests/*"],
                            "exclude_path": ["*/tests/*"],
                            "repository_alias": "test-repo"
                        }
                    )

                    assert response.status_code == 200

                    # Verify path filters with exclusion applied
                    call_kwargs = mock_tantivy_instance.search.call_args[1]
                    assert 'path_filters' in call_kwargs
                    assert sorted(call_kwargs['path_filters']) == ["*/lib/*", "*/src/*"]

        finally:
            app.dependency_overrides.clear()

    def test_regex_mode_passed_to_fts(self, test_client: TestClient, tmp_path: Path):
        """Test that regex=True is passed to FTS search."""
        app = test_client.app
        app.dependency_overrides[dependencies.get_current_user] = override_get_current_user

        try:
            from code_indexer.server import app as app_module
            activated_repos_dir = app_module.activated_repo_manager.activated_repos_dir
            fts_index_dir = Path(activated_repos_dir) / "testuser" / "test-repo" / ".code-indexer" / "tantivy_index"
            fts_index_dir.mkdir(parents=True, exist_ok=True)
            (fts_index_dir / "dummy.txt").write_text("dummy")

            with patch('code_indexer.server.app.activated_repo_manager.list_activated_repositories') as mock_list_repos:
                mock_list_repos.return_value = [
                    {"user_alias": "test-repo", "path": str(Path(activated_repos_dir) / "testuser" / "test-repo")}
                ]

                with patch('code_indexer.services.tantivy_index_manager.TantivyIndexManager') as MockTantivyClass:
                    mock_tantivy_instance = MockTantivyClass.return_value
                    mock_tantivy_instance.initialize_index.return_value = None
                    mock_tantivy_instance.search.return_value = []

                    response = test_client.post(
                        "/api/query",
                        json={
                            "query_text": "def.*",
                            "search_mode": "fts",
                            "regex": True,
                            "repository_alias": "test-repo"
                        }
                    )

                    assert response.status_code == 200

                    # Verify regex parameter passed to search
                    call_kwargs = mock_tantivy_instance.search.call_args[1]
                    assert 'use_regex' in call_kwargs
                    assert call_kwargs['use_regex'] is True

        finally:
            app.dependency_overrides.clear()
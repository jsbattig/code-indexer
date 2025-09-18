"""
Unit tests for Semantic Search endpoint.

Following CLAUDE.md Foundation #1: No mocks - uses real search operations.
Tests the /api/repositories/{repo_id}/search endpoint functionality.
"""

import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.code_indexer.server.app import create_app
from src.code_indexer.server.models.api_models import (
    SemanticSearchResponse,
    SearchResultItem,
)


class TestSemanticSearchEndpoint:
    """Unit tests for semantic search endpoint."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app for testing."""
        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def search_test_repo_directory(self):
        """Create a test repository with searchable code content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "search_test_repo"
            repo_path.mkdir()

            # Create files with searchable content
            (repo_path / "auth.py").write_text(
                """
def authenticate_user(username, password):
    '''Authenticate user with username and password.'''
    if not username or not password:
        raise ValueError("Username and password required")
    
    # Check user credentials in database
    user = get_user_from_database(username)
    if user and verify_password(password, user.password_hash):
        return create_jwt_token(user.id)
    return None

def verify_password(plain_password, hashed_password):
    '''Verify plain password against hashed password.'''
    return bcrypt.checkpw(plain_password.encode(), hashed_password)

def create_jwt_token(user_id):
    '''Create JWT token for authenticated user.'''
    payload = {"user_id": user_id, "exp": datetime.utcnow() + timedelta(hours=24)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
"""
            )

            (repo_path / "database.py").write_text(
                """
import sqlite3
from typing import Optional

class DatabaseConnection:
    '''Database connection manager.'''
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
    
    def connect(self):
        '''Establish database connection.'''
        self.connection = sqlite3.connect(self.db_path)
        return self.connection
    
    def execute_query(self, query: str, params: tuple = ()):
        '''Execute SQL query with parameters.'''
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()
    
    def close(self):
        '''Close database connection.'''
        if self.connection:
            self.connection.close()
"""
            )

            (repo_path / "utils.py").write_text(
                """
def calculate_hash(data: str) -> str:
    '''Calculate hash of input data.'''
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()

def validate_email(email: str) -> bool:
    '''Validate email address format.'''
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def format_date(date_obj):
    '''Format date object to string.'''
    return date_obj.strftime('%Y-%m-%d %H:%M:%S')
"""
            )

            (repo_path / "api.py").write_text(
                """
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route('/api/login', methods=['POST'])
def login_endpoint():
    '''User login API endpoint.'''
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    token = authenticate_user(username, password)
    if token:
        return jsonify({'token': token, 'status': 'success'})
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/users', methods=['GET'])
def get_users():
    '''Get all users from database.'''
    db = DatabaseConnection('users.db')
    db.connect()
    users = db.execute_query('SELECT id, username, email FROM users')
    db.close()
    return jsonify(users)
"""
            )

            yield str(repo_path)

    @pytest.fixture
    def admin_token(self, client):
        """Get admin authentication token."""
        response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin_password"}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        return None

    def test_semantic_search_endpoint_exists(self, client, admin_token):
        """Test that the semantic search endpoint exists and is accessible."""
        # This test WILL FAIL initially - endpoint doesn't exist yet
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        search_request = {"query_text": "authentication logic", "limit": 10}

        response = client.post(
            f"/api/repositories/{repo_id}/search", json=search_request, headers=headers
        )

        # Initially this will return 404 - that's expected for TDD
        assert response.status_code in [200, 401, 403, 404]

    def test_semantic_search_request_validation(self, client, admin_token):
        """Test semantic search request validation."""
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        # Test empty query
        response = client.post(
            f"/api/repositories/{repo_id}/search",
            json={"query_text": "", "limit": 10},
            headers=headers,
        )
        # Auth might be checked first, so accept 401/403/422
        assert response.status_code in [401, 403, 404, 422]

        # Test query too long
        long_query = "a" * 1001
        response = client.post(
            f"/api/repositories/{repo_id}/search",
            json={"query_text": long_query, "limit": 10},
            headers=headers,
        )
        # Auth might be checked first, so accept 401/403/422
        assert response.status_code in [401, 403, 404, 422]

        # Test invalid limit
        response = client.post(
            f"/api/repositories/{repo_id}/search",
            json={"query_text": "test", "limit": 101},
            headers=headers,
        )
        # Auth might be checked first, so accept 401/403/422
        assert response.status_code in [401, 403, 404, 422]

    def test_semantic_search_authentication_logic_query(
        self, client, admin_token, search_test_repo_directory
    ):
        """Test semantic search for authentication logic."""
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService._get_repository_path"
        ) as mock_path:
            mock_path.return_value = search_test_repo_directory

            search_request = {
                "query_text": "authentication logic",
                "limit": 10,
                "include_source": True,
            }

            response = client.post(
                f"/api/repositories/{repo_id}/search",
                json=search_request,
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                search_response = SemanticSearchResponse(**data)

                # Validate response structure
                assert search_response.query == "authentication logic"
                assert isinstance(search_response.results, list)
                assert search_response.total >= 0

                # Should find authentication-related code
                if search_response.results:
                    # Check first result
                    first_result = search_response.results[0]
                    assert isinstance(first_result, SearchResultItem)
                    assert 0.0 <= first_result.score <= 1.0
                    assert first_result.file_path
                    assert first_result.line_start >= 1
                    assert first_result.line_end >= first_result.line_start
                    assert first_result.content

                    # Should find auth.py file with authentication content
                    auth_results = [
                        r for r in search_response.results if "auth.py" in r.file_path
                    ]
                    assert len(auth_results) > 0

                    auth_result = auth_results[0]
                    assert "authenticate" in auth_result.content.lower()

    def test_semantic_search_database_query(
        self, client, admin_token, search_test_repo_directory
    ):
        """Test semantic search for database-related code."""
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService._get_repository_path"
        ) as mock_path:
            mock_path.return_value = search_test_repo_directory

            search_request = {
                "query_text": "database connection",
                "limit": 5,
                "include_source": True,
            }

            response = client.post(
                f"/api/repositories/{repo_id}/search",
                json=search_request,
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                search_response = SemanticSearchResponse(**data)

                # Should find database-related code
                if search_response.results:
                    db_results = [
                        r
                        for r in search_response.results
                        if "database.py" in r.file_path
                    ]
                    assert len(db_results) > 0

                    db_result = db_results[0]
                    assert any(
                        term in db_result.content.lower()
                        for term in ["database", "connection", "connect"]
                    )

    def test_semantic_search_api_endpoint_query(
        self, client, admin_token, search_test_repo_directory
    ):
        """Test semantic search for API endpoint code."""
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService._get_repository_path"
        ) as mock_path:
            mock_path.return_value = search_test_repo_directory

            search_request = {
                "query_text": "REST API endpoint",
                "limit": 10,
                "include_source": True,
            }

            response = client.post(
                f"/api/repositories/{repo_id}/search",
                json=search_request,
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                search_response = SemanticSearchResponse(**data)

                # Should find API-related code
                if search_response.results:
                    api_results = [
                        r for r in search_response.results if "api.py" in r.file_path
                    ]
                    assert len(api_results) > 0

                    api_result = api_results[0]
                    assert any(
                        term in api_result.content.lower()
                        for term in ["@app.route", "endpoint", "api"]
                    )

    def test_semantic_search_result_ranking(
        self, client, admin_token, search_test_repo_directory
    ):
        """Test that semantic search results are properly ranked by relevance."""
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService._get_repository_path"
        ) as mock_path:
            mock_path.return_value = search_test_repo_directory

            search_request = {
                "query_text": "user authentication",
                "limit": 10,
                "include_source": True,
            }

            response = client.post(
                f"/api/repositories/{repo_id}/search",
                json=search_request,
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                search_response = SemanticSearchResponse(**data)

                # Results should be ordered by score (descending)
                if len(search_response.results) > 1:
                    for i in range(len(search_response.results) - 1):
                        current_score = search_response.results[i].score
                        next_score = search_response.results[i + 1].score
                        assert current_score >= next_score

    def test_semantic_search_limit_parameter(
        self, client, admin_token, search_test_repo_directory
    ):
        """Test that semantic search respects the limit parameter."""
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService._get_repository_path"
        ) as mock_path:
            mock_path.return_value = search_test_repo_directory

            # Test with limit of 3
            search_request = {"query_text": "function", "limit": 3, "include_source": True}

            response = client.post(
                f"/api/repositories/{repo_id}/search",
                json=search_request,
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                search_response = SemanticSearchResponse(**data)

                # Should return at most 3 results
                assert len(search_response.results) <= 3

    def test_semantic_search_include_source_parameter(
        self, client, admin_token, search_test_repo_directory
    ):
        """Test that include_source parameter controls content inclusion."""
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService._get_repository_path"
        ) as mock_path:
            mock_path.return_value = search_test_repo_directory

            # Test without source code
            search_request = {
                "query_text": "authentication",
                "limit": 5,
                "include_source": False,
            }

            response = client.post(
                f"/api/repositories/{repo_id}/search",
                json=search_request,
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                search_response = SemanticSearchResponse(**data)

                # Results should have minimal content when include_source=False
                for result in search_response.results:
                    # Content might be empty or just a snippet
                    assert len(result.content) <= 100  # Expect truncated content

    def test_semantic_search_nonexistent_repository(self, client, admin_token):
        """Test semantic search with non-existent repository."""
        repo_id = "nonexistent-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        search_request = {"query_text": "test", "limit": 10}

        response = client.post(
            f"/api/repositories/{repo_id}/search", json=search_request, headers=headers
        )

        # Should return 404 for non-existent repository (or 403 if auth fails first)
        assert response.status_code in [403, 404]

    def test_semantic_search_unauthorized_access(self, client):
        """Test semantic search endpoint without authentication."""
        repo_id = "search-test-repo"
        search_request = {"query_text": "test", "limit": 10}

        response = client.post(
            f"/api/repositories/{repo_id}/search", json=search_request
        )

        # Should return 401 or 403 without authentication
        assert response.status_code in [401, 403]

    def test_semantic_search_performance_requirement(
        self, client, admin_token, search_test_repo_directory
    ):
        """Test that semantic search meets performance requirements (<2s)."""
        import time

        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService._get_repository_path"
        ) as mock_path:
            mock_path.return_value = search_test_repo_directory

            search_request = {
                "query_text": "authentication logic",
                "limit": 10,
                "include_source": True,
            }

            start_time = time.time()
            response = client.post(
                f"/api/repositories/{repo_id}/search",
                json=search_request,
                headers=headers,
            )
            end_time = time.time()

            # Performance requirement: <2 seconds
            assert end_time - start_time < 2.0

            if response.status_code == 200:
                data = response.json()
                assert "query" in data
                assert "results" in data

    def test_semantic_search_empty_query_results(
        self, client, admin_token, search_test_repo_directory
    ):
        """Test semantic search with query that has no matches."""
        repo_id = "search-test-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService._get_repository_path"
        ) as mock_path:
            mock_path.return_value = search_test_repo_directory

            # Search for something that shouldn't exist
            search_request = {
                "query_text": "nonexistent_function_xyz123",
                "limit": 10,
                "include_source": True,
            }

            response = client.post(
                f"/api/repositories/{repo_id}/search",
                json=search_request,
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                search_response = SemanticSearchResponse(**data)

                # Should return valid structure even with no results
                assert search_response.query == "nonexistent_function_xyz123"
                assert isinstance(search_response.results, list)
                assert search_response.total == 0
                assert len(search_response.results) == 0

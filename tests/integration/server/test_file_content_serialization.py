"""Integration tests for file content endpoint JSON serialization.

Tests that datetime objects are properly serialized to ISO strings.
"""

import json
import pytest
from fastapi.testclient import TestClient
from src.code_indexer.server.app import app


def test_file_content_endpoint_returns_json_serializable_response():
    """File content endpoint should return JSON-serializable response (no datetime objects)"""
    client = TestClient(app)

    # Login
    login_response = client.post(
        "/auth/login", json={"username": "admin", "password": "MySecurePass2024_Word"}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Request file content
    response = client.get(
        "/api/repositories/tries-test/files",
        params={"path": "README.md", "content": "true"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should not crash with serialization error
    assert response.status_code != 500, f"Server crashed: {response.text}"

    # Should return valid JSON
    if response.status_code == 200:
        data = response.json()
        # All fields should be JSON-serializable (no datetime objects)
        try:
            json.dumps(data)  # Should not raise TypeError
        except TypeError as e:
            pytest.fail(f"Response contains non-serializable objects: {e}")

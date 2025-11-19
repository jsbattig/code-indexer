"""Test that QueryResultItem can be imported without server initialization.

This test ensures that importing QueryResultItem doesn't trigger server app
initialization, which causes unwanted logging and slow imports.
"""

import sys


def test_query_result_item_import_no_server_init():
    """Test that importing QueryResultItem doesn't initialize server app."""
    # Clear any cached imports
    modules_to_clear = [m for m in sys.modules if "code_indexer.server" in m]
    for module in modules_to_clear:
        del sys.modules[module]

    # Import QueryResultItem from api_models (new location)
    from src.code_indexer.server.models.api_models import QueryResultItem

    # Verify server app was NOT initialized
    # If server app initialized, it would be in sys.modules
    assert (
        "src.code_indexer.server.app" not in sys.modules
    ), "Server app should not be imported when importing QueryResultItem"

    # Verify QueryResultItem is a valid class
    assert QueryResultItem is not None
    assert hasattr(QueryResultItem, "__init__")


def test_query_result_item_has_required_fields():
    """Test that QueryResultItem has all required fields."""
    from src.code_indexer.server.models.api_models import QueryResultItem

    # Create an instance to verify fields
    result = QueryResultItem(
        file_path="/test/path.py",
        line_number=42,
        code_snippet="def test(): pass",
        similarity_score=0.95,
        repository_alias="test-repo",
        file_last_modified=1699999999.0,
        indexed_timestamp=1700000000.0,
    )

    assert result.file_path == "/test/path.py"
    assert result.line_number == 42
    assert result.code_snippet == "def test(): pass"
    assert result.similarity_score == 0.95
    assert result.repository_alias == "test-repo"
    assert result.file_last_modified == 1699999999.0
    assert result.indexed_timestamp == 1700000000.0

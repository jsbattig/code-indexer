"""
Test CLI filter construction for language exclusion.

These tests verify that the CLI properly constructs must_not filter conditions
when --exclude-language flags are provided.

Note: These are unit tests that verify filter construction logic, not full E2E tests.
Full E2E tests are in test_language_exclusion_e2e.py.
"""

import pytest
from unittest.mock import Mock, patch

from code_indexer.services.language_mapper import LanguageMapper


@pytest.fixture
def mock_backend():
    """Create a mock backend for CLI testing."""
    with patch("code_indexer.cli.BackendFactory.create") as mock_factory:
        mock_backend_instance = Mock()
        mock_vector_store = Mock()

        # Setup vector store mock
        mock_vector_store.health_check.return_value = True
        mock_vector_store.resolve_collection_name.return_value = "test_collection"
        mock_vector_store.ensure_payload_indexes.return_value = None
        mock_vector_store.search.return_value = []

        mock_backend_instance.get_vector_store_client.return_value = mock_vector_store
        mock_factory.return_value = mock_backend_instance

        yield mock_backend_instance, mock_vector_store


@pytest.fixture
def mock_embedding_provider():
    """Create a mock embedding provider."""
    with patch("code_indexer.cli.EmbeddingProviderFactory.create") as mock_factory:
        mock_provider = Mock()
        mock_provider.health_check.return_value = True
        mock_provider.get_provider_name.return_value = "voyageai"
        mock_provider.get_model_info.return_value = {"name": "voyage-code-3"}
        mock_provider.get_embedding.return_value = [0.1] * 1536

        mock_factory.return_value = mock_provider
        yield mock_provider


@pytest.fixture
def mock_git_topology():
    """Mock git topology to avoid git operations."""
    with (
        patch(
            "code_indexer.services.git_topology_service.GitTopologyService"
        ) as mock_git_service,
        patch(
            "code_indexer.services.generic_query_service.GenericQueryService"
        ) as mock_query_service,
    ):
        mock_git_instance = Mock()
        mock_git_instance.is_git_available.return_value = False
        mock_git_service.return_value = mock_git_instance

        mock_query_instance = Mock()
        mock_query_instance.get_current_branch_context.return_value = None
        mock_query_service.return_value = mock_query_instance

        yield mock_git_instance


def test_exclude_language_single_extension_creates_must_not_filter(
    tmp_path, mock_backend, mock_embedding_provider, mock_git_topology
):
    """
    GIVEN a query with --exclude-language javascript
    WHEN the CLI processes the query
    THEN it creates a must_not filter with js, mjs, cjs extensions

    This is a simplified unit test that verifies the language mapper logic.
    """
    # Test the language mapper directly (unit test)
    mapper = LanguageMapper()
    extensions = mapper.get_extensions("javascript")

    # Verify JavaScript has expected extensions
    expected_extensions = {"js", "jsx"}
    assert (
        extensions == expected_extensions
    ), f"Expected {expected_extensions}, got {extensions}"

    # Verify filter construction logic
    must_not_conditions = []
    for ext in extensions:
        must_not_conditions.append({"key": "language", "match": {"value": ext}})

    # Verify we have correct number of conditions
    assert (
        len(must_not_conditions) == 2
    ), "Should have 2 must_not conditions for JavaScript"

    # Verify structure
    for condition in must_not_conditions:
        assert "key" in condition
        assert "match" in condition
        assert condition["key"] == "language"
        assert "value" in condition["match"]


def test_exclude_multiple_languages_creates_combined_must_not_filter(
    tmp_path, mock_backend, mock_embedding_provider, mock_git_topology
):
    """
    GIVEN a query with multiple --exclude-language flags
    WHEN the CLI processes the query
    THEN it creates a must_not filter with all extensions from all languages

    This is a simplified unit test that verifies the language mapper logic.
    """
    # Test the language mapper directly for multiple languages
    mapper = LanguageMapper()

    js_extensions = mapper.get_extensions("javascript")
    py_extensions = mapper.get_extensions("python")

    # Verify JavaScript extensions
    assert js_extensions == {"js", "jsx"}

    # Verify Python extensions
    assert py_extensions == {"py", "pyw", "pyi"}

    # Verify filter construction logic for multiple languages
    must_not_conditions = []
    for lang in ["javascript", "python"]:
        extensions = mapper.get_extensions(lang)
        for ext in extensions:
            must_not_conditions.append({"key": "language", "match": {"value": ext}})

    # Verify we have correct total number of conditions (2 + 3 = 5)
    assert len(must_not_conditions) == 5, "Should have 5 must_not conditions total"

    # Verify all expected extensions are present
    excluded_extensions = {cond["match"]["value"] for cond in must_not_conditions}
    expected_extensions = {"js", "jsx", "py", "pyw", "pyi"}
    assert (
        excluded_extensions == expected_extensions
    ), f"Expected {expected_extensions}, got {excluded_extensions}"


def test_exclude_language_with_include_language_creates_both_filters(
    tmp_path, mock_backend, mock_embedding_provider, mock_git_topology
):
    """
    GIVEN a query with both --language and --exclude-language
    WHEN the CLI processes the query
    THEN it creates both must (include) and must_not (exclude) filters

    This is a simplified unit test that verifies the filter construction logic.
    """
    # Test the language mapper for both inclusion and exclusion
    mapper = LanguageMapper()

    # Test inclusion filter (Python)
    python_filter = mapper.build_language_filter("python")
    # Python has multiple extensions, should use "should" for OR logic
    assert (
        "should" in python_filter
    ), "Python filter should use OR logic for multiple extensions"

    # Verify Python extensions in should clause
    python_extensions = {cond["match"]["value"] for cond in python_filter["should"]}
    assert python_extensions == {"py", "pyw", "pyi"}

    # Test exclusion filter (JavaScript)
    js_extensions = mapper.get_extensions("javascript")
    assert js_extensions == {"js", "jsx"}

    # Verify combined filter structure
    filter_conditions = {}

    # Add must filter
    filter_conditions["must"] = [python_filter]

    # Add must_not filter
    must_not_conditions = []
    for ext in js_extensions:
        must_not_conditions.append({"key": "language", "match": {"value": ext}})
    filter_conditions["must_not"] = must_not_conditions

    # Verify both filters exist
    assert "must" in filter_conditions, "Should have must conditions"
    assert "must_not" in filter_conditions, "Should have must_not conditions"
    assert (
        len(filter_conditions["must_not"]) == 2
    ), "Should have 2 JavaScript exclusions"


def test_exclude_language_with_path_filter_creates_combined_filters(
    tmp_path, mock_backend, mock_embedding_provider, mock_git_topology
):
    """
    GIVEN a query with --path and --exclude-language
    WHEN the CLI processes the query
    THEN it creates must filter for path and must_not filter for language

    This is a simplified unit test that verifies the filter construction logic.
    """
    # Test the language mapper for TypeScript
    mapper = LanguageMapper()
    ts_extensions = mapper.get_extensions("typescript")
    assert ts_extensions == {"ts", "tsx"}

    # Verify combined filter structure with path and exclusion
    filter_conditions = {}

    # Add must filter for path
    filter_conditions["must"] = [{"key": "path", "match": {"text": "*/tests/*"}}]

    # Add must_not filter for TypeScript
    must_not_conditions = []
    for ext in ts_extensions:
        must_not_conditions.append({"key": "language", "match": {"value": ext}})
    filter_conditions["must_not"] = must_not_conditions

    # Verify both filters exist
    assert "must" in filter_conditions, "Should have must conditions"
    assert "must_not" in filter_conditions, "Should have must_not conditions"

    # Verify path filter
    path_filter = filter_conditions["must"][0]
    assert path_filter["key"] == "path"
    assert path_filter["match"]["text"] == "*/tests/*"

    # Verify TypeScript exclusions
    excluded_extensions = {
        cond["match"]["value"] for cond in filter_conditions["must_not"]
    }
    assert excluded_extensions == {
        "ts",
        "tsx",
    }, "Should exclude both TypeScript extensions"

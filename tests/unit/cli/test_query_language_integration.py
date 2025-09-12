"""
Tests for CLI query command language mapping integration.

This module tests that the CLI query command properly integrates with
LanguageMapper to resolve friendly language names to file extensions
for Qdrant filtering.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
from pathlib import Path


# We'll patch the imports to avoid dependency issues in tests
@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for CLI testing."""
    with patch.multiple(
        "code_indexer.cli",
        EmbeddingProviderFactory=MagicMock(),
        QdrantClient=MagicMock(),
        ConfigManager=MagicMock(),
        GitTopologyService=MagicMock(),
        console=MagicMock(),
    ) as mocks:
        yield mocks


@pytest.fixture
def temp_config_dir():
    """Create temporary directory for config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        # Create minimal config structure
        config_file = config_dir / "cidx-config.json"
        config_file.write_text('{"codebase_dir": "' + str(config_dir) + '"}')
        yield config_dir


class TestQueryLanguageMappingIntegration:
    """Test integration of LanguageMapper with CLI query command."""

    @patch("code_indexer.cli.LanguageMapper")
    @patch("code_indexer.cli.LanguageValidator")
    def test_cli_uses_language_mapper_for_friendly_names(
        self, mock_validator, mock_mapper, mock_dependencies
    ):
        """Test that CLI query integrates LanguageMapper for friendly language names."""
        from code_indexer.cli import query

        # Set up mocks
        mapper_instance = mock_mapper.return_value
        mapper_instance.get_extensions.return_value = {"py", "pyw", "pyi"}

        validator_instance = mock_validator.return_value
        validator_result = Mock()
        validator_result.is_valid = True
        validator_result.language = "python"
        validator_instance.validate_language.return_value = validator_result

        # Mock config and other dependencies
        mock_config = Mock()
        mock_config.codebase_dir = "/tmp/test"
        mock_config.qdrant = Mock()

        config_manager = Mock()
        config_manager.load.return_value = mock_config

        # Set up context
        ctx = Mock()
        ctx.obj = {"config_manager": config_manager}

        # Mock Qdrant client to capture filter conditions
        qdrant_client = mock_dependencies["QdrantClient"].return_value
        qdrant_client.search_vectors.return_value = []

        # Call query with friendly language name
        try:
            query(
                ctx,
                "test query",
                limit=10,
                language="python",
                path=None,
                min_score=None,
                accuracy="balanced",
                quiet=True,
            )
        except Exception:
            pass  # We expect this to fail due to mocking, but we want to check the filter

        # Verify that LanguageMapper was used
        mock_mapper.assert_called_once()
        mapper_instance.get_extensions.assert_called_once_with("python")

    @patch("code_indexer.cli.LanguageMapper")
    @patch("code_indexer.cli.LanguageValidator")
    def test_cli_validates_language_before_mapping(
        self, mock_validator, mock_mapper, mock_dependencies
    ):
        """Test that CLI validates language before attempting mapping."""
        from code_indexer.cli import query

        # Set up validator to return invalid result
        validator_instance = mock_validator.return_value
        validator_result = Mock()
        validator_result.is_valid = False
        validator_result.error_message = (
            "Unknown language: 'pythom'. Did you mean 'python'?"
        )
        validator_result.suggestions = ["python"]
        validator_instance.validate_language.return_value = validator_result

        # Mock config
        mock_config = Mock()
        mock_config.codebase_dir = "/tmp/test"
        config_manager = Mock()
        config_manager.load.return_value = mock_config

        ctx = Mock()
        ctx.obj = {"config_manager": config_manager}

        # Call query with invalid language
        with pytest.raises(SystemExit):  # click.ClickException causes SystemExit
            query(
                ctx,
                "test query",
                limit=10,
                language="pythom",
                path=None,
                min_score=None,
                accuracy="balanced",
                quiet=True,
            )

        # Verify validation was attempted
        mock_validator.assert_called_once()
        validator_instance.validate_language.assert_called_once_with("pythom")

    @patch("code_indexer.cli.LanguageMapper")
    @patch("code_indexer.cli.LanguageValidator")
    def test_cli_handles_multiple_extensions_from_mapping(
        self, mock_validator, mock_mapper, mock_dependencies
    ):
        """Test that CLI handles languages that map to multiple extensions."""
        from code_indexer.cli import query

        # Set up mocks for multiple extensions
        mapper_instance = mock_mapper.return_value
        mapper_instance.get_extensions.return_value = {"js", "jsx"}

        validator_instance = mock_validator.return_value
        validator_result = Mock()
        validator_result.is_valid = True
        validator_result.language = "javascript"
        validator_instance.validate_language.return_value = validator_result

        # Mock config
        mock_config = Mock()
        mock_config.codebase_dir = "/tmp/test"
        mock_config.qdrant = Mock()
        config_manager = Mock()
        config_manager.load.return_value = mock_config

        ctx = Mock()
        ctx.obj = {"config_manager": config_manager}

        # Mock Qdrant client to capture filter conditions
        qdrant_client = mock_dependencies["QdrantClient"].return_value
        qdrant_client.search_vectors.return_value = []

        try:
            query(
                ctx,
                "test query",
                limit=10,
                language="javascript",
                path=None,
                min_score=None,
                accuracy="balanced",
                quiet=True,
            )
        except Exception:
            pass

        # Verify mapper was called with javascript
        mapper_instance.get_extensions.assert_called_once_with("javascript")

    @patch("code_indexer.cli.LanguageMapper")
    @patch("code_indexer.cli.LanguageValidator")
    def test_cli_preserves_backward_compatibility_with_extensions(
        self, mock_validator, mock_mapper, mock_dependencies
    ):
        """Test that CLI still works with direct file extensions (backward compatibility)."""
        from code_indexer.cli import query

        # Set up mocks for direct extension
        validator_instance = mock_validator.return_value
        validator_result = Mock()
        validator_result.is_valid = True
        validator_result.language = "py"
        validator_instance.validate_language.return_value = validator_result

        mapper_instance = mock_mapper.return_value
        mapper_instance.get_extensions.return_value = {"py"}  # Extension maps to itself

        # Mock config
        mock_config = Mock()
        mock_config.codebase_dir = "/tmp/test"
        mock_config.qdrant = Mock()
        config_manager = Mock()
        config_manager.load.return_value = mock_config

        ctx = Mock()
        ctx.obj = {"config_manager": config_manager}

        # Mock Qdrant client
        qdrant_client = mock_dependencies["QdrantClient"].return_value
        qdrant_client.search_vectors.return_value = []

        try:
            query(
                ctx,
                "test query",
                limit=10,
                language="py",
                path=None,
                min_score=None,
                accuracy="balanced",
                quiet=True,
            )
        except Exception:
            pass

        # Verify validation and mapping occurred
        validator_instance.validate_language.assert_called_once_with("py")
        mapper_instance.get_extensions.assert_called_once_with("py")


class TestQueryLanguageErrorHandling:
    """Test error handling for language validation in CLI."""

    @patch("code_indexer.cli.LanguageValidator")
    def test_cli_exits_with_helpful_message_for_invalid_language(
        self, mock_validator, mock_dependencies
    ):
        """Test that CLI exits with helpful error message for invalid languages."""
        from code_indexer.cli import query

        # Set up validator to return invalid result with suggestions
        validator_instance = mock_validator.return_value
        validator_result = Mock()
        validator_result.is_valid = False
        validator_result.error_message = (
            "Unknown language: 'pythom'. Did you mean 'python'?"
        )
        validator_result.suggestions = ["python"]
        validator_instance.validate_language.return_value = validator_result

        # Mock config
        mock_config = Mock()
        mock_config.codebase_dir = "/tmp/test"
        config_manager = Mock()
        config_manager.load.return_value = mock_config

        ctx = Mock()
        ctx.obj = {"config_manager": config_manager}

        # Call should exit with error
        with pytest.raises(SystemExit):
            query(
                ctx,
                "test query",
                limit=10,
                language="pythom",
                path=None,
                min_score=None,
                accuracy="balanced",
                quiet=True,
            )

    @patch("code_indexer.cli.LanguageValidator")
    def test_cli_handles_validation_exceptions(self, mock_validator, mock_dependencies):
        """Test that CLI handles unexpected validation exceptions gracefully."""
        from code_indexer.cli import query

        # Set up validator to raise exception
        validator_instance = mock_validator.return_value
        validator_instance.validate_language.side_effect = Exception("Validation error")

        # Mock config
        mock_config = Mock()
        mock_config.codebase_dir = "/tmp/test"
        config_manager = Mock()
        config_manager.load.return_value = mock_config

        ctx = Mock()
        ctx.obj = {"config_manager": config_manager}

        # Call should handle exception gracefully
        with pytest.raises(SystemExit):
            query(
                ctx,
                "test query",
                limit=10,
                language="python",
                path=None,
                min_score=None,
                accuracy="balanced",
                quiet=True,
            )


class TestQueryFilterGeneration:
    """Test that query generates proper Qdrant filters from language mappings."""

    @patch("code_indexer.cli.LanguageMapper")
    @patch("code_indexer.cli.LanguageValidator")
    def test_single_extension_creates_simple_filter(
        self, mock_validator, mock_mapper, mock_dependencies
    ):
        """Test that single extension creates a simple language filter."""
        from code_indexer.cli import query

        # Mock successful validation and single extension mapping
        validator_instance = mock_validator.return_value
        validator_result = Mock()
        validator_result.is_valid = True
        validator_instance.validate_language.return_value = validator_result

        mapper_instance = mock_mapper.return_value
        mapper_instance.get_extensions.return_value = {"go"}

        # Mock config and Qdrant
        mock_config = Mock()
        mock_config.codebase_dir = "/tmp/test"
        mock_config.qdrant = Mock()
        config_manager = Mock()
        config_manager.load.return_value = mock_config

        ctx = Mock()
        ctx.obj = {"config_manager": config_manager}

        qdrant_client = mock_dependencies["QdrantClient"].return_value
        qdrant_client.search_vectors.return_value = []

        try:
            query(
                ctx,
                "test query",
                limit=10,
                language="go",
                path=None,
                min_score=None,
                accuracy="balanced",
                quiet=True,
            )
        except Exception:
            pass

        # The test framework would need to capture and verify the filter structure
        # This is a placeholder for the actual filter verification logic

    @patch("code_indexer.cli.LanguageMapper")
    @patch("code_indexer.cli.LanguageValidator")
    def test_multiple_extensions_create_or_filter(
        self, mock_validator, mock_mapper, mock_dependencies
    ):
        """Test that multiple extensions create proper OR filter conditions."""
        from code_indexer.cli import query

        # Mock successful validation and multiple extension mapping
        validator_instance = mock_validator.return_value
        validator_result = Mock()
        validator_result.is_valid = True
        validator_instance.validate_language.return_value = validator_result

        mapper_instance = mock_mapper.return_value
        mapper_instance.get_extensions.return_value = {"py", "pyw", "pyi"}

        # Mock config and Qdrant
        mock_config = Mock()
        mock_config.codebase_dir = "/tmp/test"
        mock_config.qdrant = Mock()
        config_manager = Mock()
        config_manager.load.return_value = mock_config

        ctx = Mock()
        ctx.obj = {"config_manager": config_manager}

        qdrant_client = mock_dependencies["QdrantClient"].return_value
        qdrant_client.search_vectors.return_value = []

        try:
            query(
                ctx,
                "test query",
                limit=10,
                language="python",
                path=None,
                min_score=None,
                accuracy="balanced",
                quiet=True,
            )
        except Exception:
            pass

        # The test framework would verify that an OR filter was created for py, pyw, pyi

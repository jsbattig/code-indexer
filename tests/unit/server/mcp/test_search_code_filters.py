"""Unit tests for MCP search_code handler with new filter parameters.

Tests comprehensive parameter support for:
- language: Filter by programming language
- exclude_language: Exclude specific languages
- path_filter: Include files matching path pattern
- exclude_path: Exclude files matching path pattern
- file_extensions: Filter by file extensions (already supported, testing explicitly)
- accuracy: Search accuracy profile [fast|balanced|high]
"""

import pytest
from unittest.mock import Mock, patch
from code_indexer.server.mcp.handlers import search_code
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.role = UserRole.NORMAL_USER
    user.has_permission = Mock(return_value=True)
    return user


class TestSearchCodeLanguageFilter:
    """Test language filter parameter."""

    @pytest.mark.asyncio
    async def test_search_with_language_filter(self, mock_user):
        """Test search_code with language filter returns only specified language files."""
        with patch("code_indexer.server.app") as mock_app:
            # Mock query_user_repositories to verify language parameter is passed
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [
                    {
                        "file_path": "src/main.py",
                        "line_number": 10,
                        "code_snippet": "def authenticate():",
                        "similarity_score": 0.95,
                        "repository_alias": "test-repo",
                        "source_repo": None,
                    }
                ],
                "total_results": 1,
                "query_metadata": {
                    "query_text": "authentication",
                    "execution_time_ms": 50,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "authentication",
                "language": "python",
                "limit": 5,
            }

            result = await search_code(params, mock_user)

            # Verify language parameter was passed
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["language"] == "python"
            assert call_kwargs["query_text"] == "authentication"
            assert call_kwargs["limit"] == 5

            # Verify MCP response format
            assert "content" in result
            assert len(result["content"]) == 1
            assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_search_with_multiple_language_aliases(self, mock_user):
        """Test language filter works with various language aliases (py, js, ts, etc)."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            # Test various language aliases
            language_aliases = ["py", "python", "js", "javascript", "ts", "typescript"]
            for lang in language_aliases:
                params = {
                    "query_text": "test",
                    "language": lang,
                }

                await search_code(params, mock_user)

                # Verify language parameter was passed correctly
                call_kwargs = (
                    mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
                )
                assert call_kwargs["language"] == lang


class TestSearchCodeExcludeLanguage:
    """Test exclude_language filter parameter."""

    @pytest.mark.asyncio
    async def test_search_with_exclude_language(self, mock_user):
        """Test search_code with exclude_language filter removes specified language."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [
                    {
                        "file_path": "src/main.py",
                        "line_number": 5,
                        "code_snippet": "# Implementation code",
                        "similarity_score": 0.85,
                        "repository_alias": "test-repo",
                        "source_repo": None,
                    }
                ],
                "total_results": 1,
                "query_metadata": {
                    "query_text": "implementation",
                    "execution_time_ms": 40,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "implementation",
                "exclude_language": "markdown",
                "limit": 10,
            }

            result = await search_code(params, mock_user)

            # Verify exclude_language parameter was passed
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["exclude_language"] == "markdown"
            assert call_kwargs["query_text"] == "implementation"

            # Verify MCP response format
            assert "content" in result
            assert len(result["content"]) == 1

    @pytest.mark.asyncio
    async def test_search_with_both_language_and_exclude_language(self, mock_user):
        """Test language and exclude_language can be used together (though unusual)."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
                "language": "python",
                "exclude_language": "markdown",
            }

            await search_code(params, mock_user)

            # Both parameters should be passed through
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["language"] == "python"
            assert call_kwargs["exclude_language"] == "markdown"


class TestSearchCodePathFilter:
    """Test path_filter parameter."""

    @pytest.mark.asyncio
    async def test_search_with_path_filter(self, mock_user):
        """Test search_code with path_filter returns only matching paths."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [
                    {
                        "file_path": "tests/test_auth.py",
                        "line_number": 20,
                        "code_snippet": "def test_login():",
                        "similarity_score": 0.92,
                        "repository_alias": "test-repo",
                        "source_repo": None,
                    }
                ],
                "total_results": 1,
                "query_metadata": {
                    "query_text": "test login",
                    "execution_time_ms": 35,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test login",
                "path_filter": "*/tests/*",
                "limit": 5,
            }

            result = await search_code(params, mock_user)

            # Verify path_filter parameter was passed
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["path_filter"] == "*/tests/*"

            # Verify MCP response format
            assert "content" in result
            assert len(result["content"]) == 1

    @pytest.mark.asyncio
    async def test_search_with_complex_path_patterns(self, mock_user):
        """Test path_filter with various glob patterns."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            # Test various glob patterns
            patterns = [
                "*/tests/*",
                "*/src/**/*.py",
                "**/*.js",
                "src/components/*",
                "**/test_*.py",
            ]

            for pattern in patterns:
                params = {
                    "query_text": "test",
                    "path_filter": pattern,
                }

                await search_code(params, mock_user)

                # Verify pattern was passed correctly
                call_kwargs = (
                    mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
                )
                assert call_kwargs["path_filter"] == pattern


class TestSearchCodeExcludePath:
    """Test exclude_path parameter."""

    @pytest.mark.asyncio
    async def test_search_with_exclude_path(self, mock_user):
        """Test search_code with exclude_path removes matching paths."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [
                    {
                        "file_path": "src/main.py",
                        "line_number": 15,
                        "code_snippet": "def production_code():",
                        "similarity_score": 0.88,
                        "repository_alias": "test-repo",
                        "source_repo": None,
                    }
                ],
                "total_results": 1,
                "query_metadata": {
                    "query_text": "production code",
                    "execution_time_ms": 45,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "production code",
                "exclude_path": "*/tests/*",
                "limit": 10,
            }

            result = await search_code(params, mock_user)

            # Verify exclude_path parameter was passed
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["exclude_path"] == "*/tests/*"

            # Verify MCP response format
            assert "content" in result

    @pytest.mark.asyncio
    async def test_search_with_exclude_minified_files(self, mock_user):
        """Test exclude_path with minified file patterns."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
                "exclude_path": "*.min.js",
            }

            await search_code(params, mock_user)

            # Verify exclude pattern was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["exclude_path"] == "*.min.js"


class TestSearchCodeFileExtensions:
    """Test file_extensions parameter (already exists, testing explicitly)."""

    @pytest.mark.asyncio
    async def test_search_with_file_extensions(self, mock_user):
        """Test search_code with file_extensions filter."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [
                    {
                        "file_path": "src/main.py",
                        "line_number": 10,
                        "code_snippet": "class MyClass:",
                        "similarity_score": 0.90,
                        "repository_alias": "test-repo",
                        "source_repo": None,
                    }
                ],
                "total_results": 1,
                "query_metadata": {
                    "query_text": "class definition",
                    "execution_time_ms": 30,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "class definition",
                "file_extensions": [".py", ".js"],
                "limit": 10,
            }

            result = await search_code(params, mock_user)

            # Verify file_extensions parameter was passed
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["file_extensions"] == [".py", ".js"]

            # Verify MCP response format
            assert "content" in result


class TestSearchCodeAccuracy:
    """Test accuracy parameter."""

    @pytest.mark.asyncio
    async def test_search_with_accuracy_fast(self, mock_user):
        """Test search_code with accuracy=fast."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 5,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
                "accuracy": "fast",
            }

            await search_code(params, mock_user)

            # Verify accuracy parameter was passed
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["accuracy"] == "fast"

    @pytest.mark.asyncio
    async def test_search_with_accuracy_balanced(self, mock_user):
        """Test search_code with accuracy=balanced (default)."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 15,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
                "accuracy": "balanced",
            }

            await search_code(params, mock_user)

            # Verify accuracy parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["accuracy"] == "balanced"

    @pytest.mark.asyncio
    async def test_search_with_accuracy_high(self, mock_user):
        """Test search_code with accuracy=high."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 30,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
                "accuracy": "high",
            }

            await search_code(params, mock_user)

            # Verify accuracy parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["accuracy"] == "high"

    @pytest.mark.asyncio
    async def test_search_accuracy_defaults_to_balanced(self, mock_user):
        """Test search_code defaults to balanced accuracy when not specified."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 15,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
            }

            await search_code(params, mock_user)

            # Verify accuracy defaults to "balanced"
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["accuracy"] == "balanced"


class TestSearchCodeCombinedFilters:
    """Test combinations of filter parameters."""

    @pytest.mark.asyncio
    async def test_search_with_all_filters_combined(self, mock_user):
        """Test search_code with all filter parameters used together."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [
                    {
                        "file_path": "src/auth/login.py",
                        "line_number": 25,
                        "code_snippet": "def authenticate_user():",
                        "similarity_score": 0.95,
                        "repository_alias": "test-repo",
                        "source_repo": None,
                    }
                ],
                "total_results": 1,
                "query_metadata": {
                    "query_text": "authentication",
                    "execution_time_ms": 50,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "authentication",
                "language": "python",
                "path_filter": "*/src/*",
                "exclude_path": "*/tests/*",
                "accuracy": "high",
                "limit": 10,
                "min_score": 0.8,
            }

            result = await search_code(params, mock_user)

            # Verify ALL parameters were passed correctly
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["query_text"] == "authentication"
            assert call_kwargs["language"] == "python"
            assert call_kwargs["path_filter"] == "*/src/*"
            assert call_kwargs["exclude_path"] == "*/tests/*"
            assert call_kwargs["accuracy"] == "high"
            assert call_kwargs["limit"] == 10
            assert call_kwargs["min_score"] == 0.8

            # Verify MCP response format
            assert "content" in result
            assert len(result["content"]) == 1

    @pytest.mark.asyncio
    async def test_search_with_language_and_path_filters(self, mock_user):
        """Test common combination: language + path filters."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 20,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
                "language": "python",
                "path_filter": "*/src/**/*.py",
            }

            await search_code(params, mock_user)

            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["language"] == "python"
            assert call_kwargs["path_filter"] == "*/src/**/*.py"

    @pytest.mark.asyncio
    async def test_search_with_exclusion_filters(self, mock_user):
        """Test combination of exclusion filters."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 15,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
                "exclude_language": "markdown",
                "exclude_path": "*/node_modules/*",
            }

            await search_code(params, mock_user)

            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["exclude_language"] == "markdown"
            assert call_kwargs["exclude_path"] == "*/node_modules/*"


class TestSearchCodeBackwardCompatibility:
    """Test backward compatibility with existing parameters."""

    @pytest.mark.asyncio
    async def test_search_without_new_parameters_still_works(self, mock_user):
        """Test that search works without any new parameters (backward compatible)."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            # Old-style parameters only
            params = {
                "query_text": "test",
                "limit": 10,
                "min_score": 0.5,
            }

            result = await search_code(params, mock_user)

            # Verify it still works (new parameters should be None)
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["query_text"] == "test"
            assert call_kwargs["limit"] == 10
            assert call_kwargs["min_score"] == 0.5
            assert call_kwargs.get("language") is None
            assert call_kwargs.get("exclude_language") is None
            assert call_kwargs.get("path_filter") is None
            assert call_kwargs.get("exclude_path") is None

            # Verify MCP response format
            assert "content" in result


class TestSearchCodeErrorHandling:
    """Test error handling with new parameters."""

    @pytest.mark.asyncio
    async def test_search_with_invalid_accuracy_value(self, mock_user):
        """Test that invalid accuracy values are handled (backend validates)."""
        with patch("code_indexer.server.app") as mock_app:
            # Backend should handle validation, but handler passes through
            mock_app.semantic_query_manager.query_user_repositories.side_effect = (
                ValueError("Invalid accuracy value")
            )

            params = {
                "query_text": "test",
                "accuracy": "invalid",
            }

            result = await search_code(params, mock_user)

            # Error should be caught and returned in MCP format
            assert "content" in result
            content = result["content"][0]
            assert "success" in content["text"]
            # Result should indicate failure

    @pytest.mark.asyncio
    async def test_search_handles_backend_failures_gracefully(self, mock_user):
        """Test that backend failures are handled gracefully."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.side_effect = (
                Exception("Backend error")
            )

            params = {
                "query_text": "test",
                "language": "python",
            }

            result = await search_code(params, mock_user)

            # Should return error in MCP format
            assert "content" in result
            assert len(result["content"]) == 1

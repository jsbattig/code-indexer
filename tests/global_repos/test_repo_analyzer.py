"""
Tests for AC3: AI Description Generation via RepoAnalyzer.

Tests that RepoAnalyzer can extract information from various
repository sources (README, package files, directory structure).

Also tests Anthropic SDK integration for enhanced metadata generation.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.global_repos.repo_analyzer import RepoAnalyzer, RepoInfo


class TestRepoAnalyzer:
    """Test suite for repository analysis and information extraction."""

    @pytest.fixture(autouse=True)
    def disable_claude_for_static_tests(self):
        """Disable Claude CLI for static analysis tests to prevent subprocess hangs."""
        with patch.dict(os.environ, {"CIDX_USE_CLAUDE_FOR_META": "false"}):
            yield

    def test_analyze_repo_with_readme(self, tmp_path):
        """
        Test that analyzer extracts info from README.md.

        AC3: Analyze README.md if present
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        # Create README with content
        readme = repo_dir / "README.md"
        readme.write_text(
            """
# My Awesome Project

A Python library for authentication and authorization.

## Features
- JWT token authentication
- OAuth2 integration
- Role-based access control
"""
        )

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        assert info.summary is not None
        assert len(info.summary) > 0
        assert (
            "authentication" in info.summary.lower()
            or "authorization" in info.summary.lower()
        )

    def test_analyze_python_repo_from_setup_py(self, tmp_path):
        """
        Test that analyzer extracts dependencies from setup.py.

        AC3: Analyze package.json/setup.py/Cargo.toml for dependencies
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        # Create setup.py
        setup_py = repo_dir / "setup.py"
        setup_py.write_text(
            """
from setuptools import setup

setup(
    name="test-package",
    install_requires=[
        "fastapi>=0.68.0",
        "pydantic>=1.8.0",
        "pytest>=6.0.0"
    ]
)
"""
        )

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        # Should detect Python
        assert "Python" in info.technologies

    def test_analyze_python_repo_from_pyproject_toml(self, tmp_path):
        """
        Test that analyzer extracts dependencies from pyproject.toml.

        AC3: Analyze package files for dependencies
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        # Create pyproject.toml
        pyproject = repo_dir / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-package"
dependencies = [
    "fastapi>=0.68.0",
    "pydantic>=1.8.0"
]
"""
        )

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        assert "Python" in info.technologies

    def test_analyze_javascript_repo_from_package_json(self, tmp_path):
        """
        Test that analyzer extracts dependencies from package.json.

        AC3: Analyze package.json for dependencies
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        # Create package.json
        package_json = repo_dir / "package.json"
        package_json.write_text(
            """
{
  "name": "test-package",
  "dependencies": {
    "express": "^4.17.1",
    "react": "^17.0.0"
  }
}
"""
        )

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        assert "JavaScript" in info.technologies or "Node.js" in info.technologies

    def test_analyze_rust_repo_from_cargo_toml(self, tmp_path):
        """
        Test that analyzer extracts dependencies from Cargo.toml.

        AC3: Analyze Cargo.toml for dependencies
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        # Create Cargo.toml
        cargo_toml = repo_dir / "Cargo.toml"
        cargo_toml.write_text(
            """
[package]
name = "test-package"

[dependencies]
serde = "1.0"
tokio = "1.0"
"""
        )

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        assert "Rust" in info.technologies

    def test_analyze_directory_structure_for_technology_hints(self, tmp_path):
        """
        Test that analyzer infers technologies from directory structure.

        AC3: Analyze directory structure for technology hints
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        # Create Python project structure
        (repo_dir / "src").mkdir()
        (repo_dir / "src" / "__init__.py").touch()
        (repo_dir / "tests").mkdir()
        (repo_dir / "tests" / "test_main.py").touch()

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        assert "Python" in info.technologies

    def test_handle_repo_without_readme_gracefully(self, tmp_path):
        """
        Test that analyzer handles repos without README.

        AC3: Handle repos without README gracefully (infer from code)
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        # Create minimal Python structure
        (repo_dir / "main.py").write_text("print('hello')")

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        # Should still produce some info
        assert info is not None
        assert isinstance(info.technologies, list)
        assert isinstance(info.features, list)

    def test_extract_features_from_readme(self, tmp_path):
        """
        Test that analyzer extracts features from README.

        AC3: Includes relevant keywords, technologies, and purpose
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        readme = repo_dir / "README.md"
        readme.write_text(
            """
# Test Project

## Features
- Authentication
- Authorization
- Rate limiting
"""
        )

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        assert len(info.features) > 0

    def test_extract_use_cases_from_readme(self, tmp_path):
        """
        Test that analyzer extracts use cases from README.

        AC3: Generate description targeting semantic search use cases
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        readme = repo_dir / "README.md"
        readme.write_text(
            """
# Test Project

## Use Cases
- User authentication
- API key management
"""
        )

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        assert len(info.use_cases) > 0

    def test_infer_purpose_from_name_and_content(self, tmp_path):
        """
        Test that analyzer infers repository purpose.

        AC3: Includes purpose
        """
        repo_dir = tmp_path / "auth-service"
        repo_dir.mkdir()

        readme = repo_dir / "README.md"
        readme.write_text(
            """
# Auth Service

Authentication service for microservices architecture.
"""
        )

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer.extract_info()

        assert info.purpose is not None
        assert len(info.purpose) > 0


class TestClaudeCLIIntegration:
    """Test suite for Anthropic SDK integration in RepoAnalyzer."""

    @pytest.fixture
    def sample_claude_response(self):
        """Provide a sample valid Claude SDK JSON response."""
        return {
            "summary": "A comprehensive authentication library for Python applications.",
            "technologies": ["Python", "FastAPI", "JWT", "OAuth2"],
            "features": [
                "Token authentication",
                "Role-based access",
                "API key management",
            ],
            "use_cases": ["Web app authentication", "Microservice authorization"],
            "purpose": "library",
        }

    def test_extract_info_with_claude_success(self, tmp_path, sample_claude_response):
        """
        Test successful Claude SDK response parsing.

        When Claude SDK returns valid JSON, it should be parsed into RepoInfo.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Test Project\nSome description.")

        # Mock Anthropic SDK response
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(sample_claude_response))]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-api-key"}):
            with patch(
                "anthropic.Anthropic", return_value=mock_client
            ) as mock_anthropic:
                analyzer = RepoAnalyzer(str(repo_dir))
                info = analyzer._extract_info_with_claude()

                # Verify Anthropic client was created
                mock_anthropic.assert_called_once_with(api_key="test-api-key")

                # Verify messages.create was called
                mock_client.messages.create.assert_called_once()
                call_kwargs = mock_client.messages.create.call_args[1]
                assert call_kwargs["model"] == "claude-sonnet-4-20250514"
                assert call_kwargs["max_tokens"] == 1024

                # Verify parsed result
                assert info is not None
                assert (
                    info.summary
                    == "A comprehensive authentication library for Python applications."
                )
                assert "Python" in info.technologies
                assert "FastAPI" in info.technologies
                assert len(info.features) == 3
                assert len(info.use_cases) == 2
                assert info.purpose == "library"

    def test_extract_info_with_claude_cli_not_found(self, tmp_path):
        """
        Test fallback when ANTHROPIC_API_KEY is not set.

        Should return None when API key is missing.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        with patch.dict(os.environ, {}, clear=True):
            analyzer = RepoAnalyzer(str(repo_dir))
            result = analyzer._extract_info_with_claude()

            assert result is None

    def test_extract_info_with_claude_timeout(self, tmp_path):
        """
        Test fallback when Anthropic API raises an error.

        Should return None when API error occurs.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Test")

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API timeout")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                analyzer = RepoAnalyzer(str(repo_dir))
                result = analyzer._extract_info_with_claude()

                assert result is None

    def test_extract_info_with_claude_invalid_json(self, tmp_path):
        """
        Test fallback when Claude SDK returns invalid JSON.

        Should return None when JSON parsing fails.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Test")

        # Mock SDK to return invalid JSON
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="This is not valid JSON at all")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                analyzer = RepoAnalyzer(str(repo_dir))
                result = analyzer._extract_info_with_claude()

                assert result is None

    def test_extract_info_with_claude_nonzero_exit(self, tmp_path):
        """
        Test fallback when Anthropic API raises exception.

        Should return None when API call fails.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Test")

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                analyzer = RepoAnalyzer(str(repo_dir))
                result = analyzer._extract_info_with_claude()

                assert result is None

    def test_extract_info_with_claude_missing_fields(self, tmp_path):
        """
        Test handling of Claude response with missing required fields.

        Should return None if essential fields are missing.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Test")

        # Missing 'summary' field
        incomplete_response = json.dumps(
            {
                "technologies": ["Python"],
                "features": [],
                "use_cases": [],
                "purpose": "library",
            }
        )

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=incomplete_response)]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                analyzer = RepoAnalyzer(str(repo_dir))
                result = analyzer._extract_info_with_claude()

                assert result is None


class TestClaudeFallbackBehavior:
    """Test suite for Anthropic SDK fallback to static analysis."""

    def test_extract_info_uses_claude_by_default(self, tmp_path):
        """
        Test that extract_info() tries Claude first by default.

        When CIDX_USE_CLAUDE_FOR_META is not set or is 'true',
        Claude should be tried first.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Test\nDescription.")

        claude_response = {
            "summary": "Claude-generated summary",
            "technologies": ["Python"],
            "features": ["Feature A"],
            "use_cases": ["Use case 1"],
            "purpose": "library",
        }

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(claude_response))]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        # Ensure env var is true or not set
        with patch.dict(
            os.environ,
            {"CIDX_USE_CLAUDE_FOR_META": "true", "ANTHROPIC_API_KEY": "test-key"},
        ):
            with patch("anthropic.Anthropic", return_value=mock_client):
                analyzer = RepoAnalyzer(str(repo_dir))
                info = analyzer.extract_info()

                assert info.summary == "Claude-generated summary"

    def test_extract_info_falls_back_on_claude_failure(self, tmp_path):
        """
        Test that extract_info() falls back to static analysis on Claude failure.

        When Claude SDK fails, static analysis should be used.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "setup.py").write_text("from setuptools import setup")
        (repo_dir / "README.md").write_text(
            "# Test Project\n\nA Python library for testing."
        )

        with patch.dict(os.environ, {"CIDX_USE_CLAUDE_FOR_META": "true"}):
            # No API key set - Claude should fail
            with patch.dict(os.environ, {}, clear=True):
                with patch.dict(os.environ, {"CIDX_USE_CLAUDE_FOR_META": "true"}):
                    analyzer = RepoAnalyzer(str(repo_dir))
                    info = analyzer.extract_info()

                    # Should fall back to static analysis
                    assert info is not None
                    assert "Python" in info.technologies
                    # Static analysis produces different summary
                    assert (
                        "testing" in info.summary.lower()
                        or "library" in info.summary.lower()
                    )

    def test_extract_info_disabled_via_env_var(self, tmp_path):
        """
        Test that CIDX_USE_CLAUDE_FOR_META=false skips Claude.

        When the env var is set to 'false', Claude should not be called.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "setup.py").write_text("from setuptools import setup")
        (repo_dir / "README.md").write_text("# Test\n\nStatic analysis test.")

        with patch.dict(os.environ, {"CIDX_USE_CLAUDE_FOR_META": "false"}):
            with patch("anthropic.Anthropic") as mock_anthropic:
                analyzer = RepoAnalyzer(str(repo_dir))
                info = analyzer.extract_info()

                # Anthropic SDK should NOT be instantiated
                mock_anthropic.assert_not_called()

                # Static analysis should provide results
                assert info is not None
                assert "Python" in info.technologies

    def test_static_analysis_method_available(self, tmp_path):
        """
        Test that _extract_info_static() method exists and works.

        The renamed static analysis method should be callable directly.
        """
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        (repo_dir / "package.json").write_text('{"name": "test", "dependencies": {}}')

        analyzer = RepoAnalyzer(str(repo_dir))
        info = analyzer._extract_info_static()

        assert info is not None
        assert isinstance(info, RepoInfo)
        assert "JavaScript" in info.technologies or "Node.js" in info.technologies

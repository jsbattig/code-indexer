"""
Tests for AC3: AI Description Generation via RepoAnalyzer.

Tests that RepoAnalyzer can extract information from various
repository sources (README, package files, directory structure).
"""

from code_indexer.global_repos.repo_analyzer import RepoAnalyzer


class TestRepoAnalyzer:
    """Test suite for repository analysis and information extraction."""

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

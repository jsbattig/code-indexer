"""Unit tests for SCIP project discovery."""

from pathlib import Path
from code_indexer.scip.discovery import ProjectDiscovery


class TestProjectDiscovery:
    """Test project auto-discovery functionality."""

    def test_discover_projects_in_simple_repo(self, tmp_path):
        """Test discovering projects with different build systems in a simple repo."""
        # Arrange: Create a repository with multiple projects
        (tmp_path / "backend" / "pom.xml").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "backend" / "pom.xml").write_text("<project></project>")

        (tmp_path / "frontend" / "package.json").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "frontend" / "package.json").write_text('{"name": "frontend"}')

        (tmp_path / "python-lib" / "pyproject.toml").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "python-lib" / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "python-lib"'
        )

        # Act: Discover projects
        discovery = ProjectDiscovery(tmp_path)
        projects = discovery.discover()

        # Assert: All projects discovered with correct metadata
        assert len(projects) == 3

        # Check backend project
        backend = next(p for p in projects if p.relative_path == Path("backend"))
        assert backend.language == "java"
        assert backend.build_system == "maven"
        assert backend.build_file == Path("backend/pom.xml")

        # Check frontend project
        frontend = next(p for p in projects if p.relative_path == Path("frontend"))
        assert frontend.language == "typescript"
        assert frontend.build_system == "npm"
        assert frontend.build_file == Path("frontend/package.json")

        # Check python-lib project
        python_lib = next(p for p in projects if p.relative_path == Path("python-lib"))
        assert python_lib.language == "python"
        assert python_lib.build_system == "poetry"
        assert python_lib.build_file == Path("python-lib/pyproject.toml")

    def test_discover_nested_projects(self, tmp_path):
        """Test discovering nested projects (monorepo scenario)."""
        # Arrange: Create nested project structure
        (tmp_path / "services" / "api" / "pom.xml").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "services" / "api" / "pom.xml").write_text("<project></project>")

        (tmp_path / "services" / "worker" / "pom.xml").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "services" / "worker" / "pom.xml").write_text("<project></project>")

        (tmp_path / "frontend" / "package.json").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "frontend" / "package.json").write_text('{"name": "frontend"}')

        # Act: Discover projects
        discovery = ProjectDiscovery(tmp_path)
        projects = discovery.discover()

        # Assert: All nested projects discovered
        assert len(projects) == 3
        project_paths = {p.relative_path for p in projects}
        assert Path("services/api") in project_paths
        assert Path("services/worker") in project_paths
        assert Path("frontend") in project_paths

    def test_discover_gradle_projects(self, tmp_path):
        """Test discovering Gradle-based Java/Kotlin projects."""
        # Arrange: Create Gradle projects
        (tmp_path / "java-service" / "build.gradle").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "java-service" / "build.gradle").write_text("// Gradle build")

        (tmp_path / "kotlin-service" / "build.gradle.kts").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "kotlin-service" / "build.gradle.kts").write_text(
            "// Kotlin DSL Gradle"
        )

        # Act: Discover projects
        discovery = ProjectDiscovery(tmp_path)
        projects = discovery.discover()

        # Assert: Gradle projects discovered with correct language
        assert len(projects) == 2

        java_service = next(
            p for p in projects if p.relative_path == Path("java-service")
        )
        assert java_service.language == "java"
        assert java_service.build_system == "gradle"

        kotlin_service = next(
            p for p in projects if p.relative_path == Path("kotlin-service")
        )
        assert kotlin_service.language == "kotlin"
        assert kotlin_service.build_system == "gradle"

    def test_discover_python_setuptools(self, tmp_path):
        """Test discovering Python projects with setup.py."""
        # Arrange: Create setup.py project
        (tmp_path / "python-pkg" / "setup.py").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "python-pkg" / "setup.py").write_text(
            "from setuptools import setup"
        )

        # Act: Discover projects
        discovery = ProjectDiscovery(tmp_path)
        projects = discovery.discover()

        # Assert: setuptools project discovered
        assert len(projects) == 1
        python_pkg = projects[0]
        assert python_pkg.language == "python"
        assert python_pkg.build_system == "setuptools"
        assert python_pkg.relative_path == Path("python-pkg")

    def test_discover_python_requirements_txt(self, tmp_path):
        """Test discovering Python projects with only requirements.txt."""
        # Arrange: Create Python web app with requirements.txt (no setup.py/pyproject.toml)
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True, exist_ok=True)
        (backend_dir / "requirements.txt").write_text("flask==2.0.1\nfastapi==0.68.0")
        (backend_dir / "main.py").write_text("print('hello')")

        # Act: Discover projects
        discovery = ProjectDiscovery(tmp_path)
        projects = discovery.discover()

        # Assert: requirements.txt project discovered
        assert len(projects) == 1
        backend = projects[0]
        assert backend.language == "python"
        assert backend.build_system == "pip"
        assert backend.relative_path == Path("backend")
        assert backend.build_file == Path("backend/requirements.txt")

    def test_discover_empty_repo(self, tmp_path):
        """Test discovering projects in empty repository."""
        # Arrange: Empty directory

        # Act: Discover projects
        discovery = ProjectDiscovery(tmp_path)
        projects = discovery.discover()

        # Assert: No projects found
        assert len(projects) == 0

    def test_discover_python_with_multiple_build_files(self, tmp_path):
        """Test discovering Python project with multiple build files uses priority."""
        # Arrange: Create Python project with all three build files
        python_dir = tmp_path / "python-pkg"
        python_dir.mkdir(parents=True, exist_ok=True)
        (python_dir / "pyproject.toml").write_text('[tool.poetry]\nname = "python-pkg"')
        (python_dir / "setup.py").write_text("from setuptools import setup")
        (python_dir / "requirements.txt").write_text("flask==2.0.1")

        # Act: Discover projects
        discovery = ProjectDiscovery(tmp_path)
        projects = discovery.discover()

        # Assert: Only ONE project discovered using highest priority build file
        assert len(projects) == 1
        python_pkg = projects[0]
        assert python_pkg.language == "python"
        assert python_pkg.build_system == "poetry"
        assert python_pkg.build_file == Path("python-pkg/pyproject.toml")

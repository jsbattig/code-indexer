"""Unit tests for SCIP indexers."""

from pathlib import Path
from unittest.mock import Mock, patch
from code_indexer.scip.indexers.base import IndexerResult, IndexerStatus
from code_indexer.scip.indexers.java import JavaIndexer
from code_indexer.scip.indexers.typescript import TypeScriptIndexer
from code_indexer.scip.indexers.python import PythonIndexer
from code_indexer.scip.indexers.go import GoIndexer


class TestSCIPIndexerBase:
    """Test base SCIP indexer interface."""

    def test_indexer_result_success(self):
        """Test successful indexer result."""
        result = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=Path("/path/to/index.scip"),
            stdout="Indexing complete",
            stderr="",
            exit_code=0,
        )
        assert result.status == IndexerStatus.SUCCESS
        assert result.is_success()
        assert not result.is_failure()

    def test_indexer_result_failure(self):
        """Test failed indexer result."""
        result = IndexerResult(
            status=IndexerStatus.FAILED,
            duration_seconds=1.0,
            output_file=None,
            stdout="",
            stderr="Error: build failed",
            exit_code=1,
        )
        assert result.status == IndexerStatus.FAILED
        assert result.is_failure()
        assert not result.is_success()


class TestJavaIndexer:
    """Test Java/scip-java indexer."""

    @patch("code_indexer.scip.indexers.java.shutil.move")
    @patch("subprocess.run")
    def test_java_maven_indexing_success(self, mock_run, mock_move, tmp_path):
        """Test successful Maven project indexing."""
        # Arrange
        project_dir = tmp_path / "backend"
        project_dir.mkdir()
        (project_dir / "pom.xml").write_text("<project></project>")

        # Create mock .scip file
        scip_file = project_dir / "index.scip"
        scip_file.write_text("mock scip data")

        output_dir = tmp_path / ".code-indexer" / "scip" / "backend"

        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")

        # Act
        indexer = JavaIndexer()
        result = indexer.generate(project_dir, output_dir, "maven")

        # Assert
        assert result.is_success()
        assert result.exit_code == 0
        assert mock_run.called
        assert mock_move.called
        # Verify scip-java was called with Maven
        args = mock_run.call_args[0][0]
        assert "cs" in args  # coursier

    @patch("code_indexer.scip.indexers.java.shutil.move")
    @patch("subprocess.run")
    def test_java_gradle_indexing_success(self, mock_run, mock_move, tmp_path):
        """Test successful Gradle project indexing."""
        # Arrange
        project_dir = tmp_path / "service"
        project_dir.mkdir()
        (project_dir / "build.gradle").write_text("// Gradle")

        # Create mock .scip file
        scip_file = project_dir / "index.scip"
        scip_file.write_text("mock scip data")

        output_dir = tmp_path / ".code-indexer" / "scip" / "service"

        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")

        # Act
        indexer = JavaIndexer()
        result = indexer.generate(project_dir, output_dir, "gradle")

        # Assert
        assert result.is_success()
        assert mock_run.called

    @patch("subprocess.run")
    def test_java_indexing_failure(self, mock_run, tmp_path):
        """Test failed Java project indexing."""
        # Arrange
        project_dir = tmp_path / "backend"
        project_dir.mkdir()
        output_dir = tmp_path / ".code-indexer" / "scip" / "backend"

        mock_run.return_value = Mock(
            returncode=1, stdout="", stderr="Error: compilation failed"
        )

        # Act
        indexer = JavaIndexer()
        result = indexer.generate(project_dir, output_dir, "maven")

        # Assert
        assert result.is_failure()
        assert result.exit_code == 1
        assert "compilation failed" in result.stderr


class TestTypeScriptIndexer:
    """Test TypeScript/scip-typescript indexer."""

    @patch("code_indexer.scip.indexers.typescript.shutil.move")
    @patch("subprocess.run")
    def test_typescript_indexing_success(self, mock_run, mock_move, tmp_path):
        """Test successful TypeScript project indexing."""
        # Arrange
        project_dir = tmp_path / "frontend"
        project_dir.mkdir()
        (project_dir / "package.json").write_text('{"name": "frontend"}')
        (project_dir / "tsconfig.json").write_text("{}")

        # Create mock .scip file
        scip_file = project_dir / "index.scip"
        scip_file.write_text("mock scip data")

        output_dir = tmp_path / ".code-indexer" / "scip" / "frontend"

        mock_run.return_value = Mock(returncode=0, stdout="Indexed", stderr="")

        # Act
        indexer = TypeScriptIndexer()
        result = indexer.generate(project_dir, output_dir, "npm")

        # Assert
        assert result.is_success()
        assert mock_run.called
        assert mock_move.called
        args = mock_run.call_args[0][0]
        assert "scip-typescript" in args


class TestPythonIndexer:
    """Test Python/scip-python indexer."""

    @patch("code_indexer.scip.indexers.python.shutil.move")
    @patch("subprocess.run")
    def test_python_indexing_success(self, mock_run, mock_move, tmp_path):
        """Test successful Python project indexing."""
        # Arrange
        project_dir = tmp_path / "python-lib"
        project_dir.mkdir()
        (project_dir / "pyproject.toml").write_text('[tool.poetry]\nname = "lib"')

        # Create mock .scip file
        scip_file = project_dir / "index.scip"
        scip_file.write_text("mock scip data")

        output_dir = tmp_path / ".code-indexer" / "scip" / "python-lib"

        mock_run.return_value = Mock(returncode=0, stdout="Done", stderr="")

        # Act
        indexer = PythonIndexer()
        result = indexer.generate(project_dir, output_dir, "poetry")

        # Assert
        assert result.is_success()
        assert mock_run.called
        assert mock_move.called
        args = mock_run.call_args[0][0]
        assert "scip-python" in args


class TestCSharpIndexer:
    """Test C#/scip-dotnet indexer."""

    @patch("code_indexer.scip.indexers.csharp.shutil.move")
    @patch("subprocess.run")
    def test_csharp_solution_indexing_success(self, mock_run, mock_move, tmp_path):
        """Test successful C# solution project indexing."""
        # Arrange
        project_dir = tmp_path / "dotnet-app"
        project_dir.mkdir()
        (project_dir / "MyApp.sln").write_text("Microsoft Visual Studio Solution")

        # Create mock .scip file
        scip_file = project_dir / "index.scip"
        scip_file.write_text("mock scip data")

        output_dir = tmp_path / ".code-indexer" / "scip" / "dotnet-app"

        mock_run.return_value = Mock(returncode=0, stdout="Indexed", stderr="")

        # Act
        from code_indexer.scip.indexers.csharp import CSharpIndexer

        indexer = CSharpIndexer()
        result = indexer.generate(project_dir, output_dir, "solution")

        # Assert
        assert result.is_success()
        assert result.exit_code == 0
        assert mock_run.called
        assert mock_move.called
        args = mock_run.call_args[0][0]
        assert "scip-dotnet" in args
        assert "index" in args

    @patch("code_indexer.scip.indexers.csharp.shutil.move")
    @patch("subprocess.run")
    def test_csharp_project_indexing_success(self, mock_run, mock_move, tmp_path):
        """Test successful C# project file indexing."""
        # Arrange
        project_dir = tmp_path / "dotnet-lib"
        project_dir.mkdir()
        (project_dir / "MyLib.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk"></Project>'
        )

        # Create mock .scip file
        scip_file = project_dir / "index.scip"
        scip_file.write_text("mock scip data")

        output_dir = tmp_path / ".code-indexer" / "scip" / "dotnet-lib"

        mock_run.return_value = Mock(returncode=0, stdout="Indexed", stderr="")

        # Act
        from code_indexer.scip.indexers.csharp import CSharpIndexer

        indexer = CSharpIndexer()
        result = indexer.generate(project_dir, output_dir, "project")

        # Assert
        assert result.is_success()
        assert result.exit_code == 0
        assert mock_run.called
        assert mock_move.called
        args = mock_run.call_args[0][0]
        assert "scip-dotnet" in args
        assert "index" in args
        # Verify it uses current directory for project build system
        assert "." in args

    @patch("subprocess.run")
    def test_csharp_indexing_failure(self, mock_run, tmp_path):
        """Test failed C# project indexing."""
        # Arrange
        project_dir = tmp_path / "dotnet-app"
        project_dir.mkdir()
        (project_dir / "MyApp.sln").write_text("Microsoft Visual Studio Solution")
        output_dir = tmp_path / ".code-indexer" / "scip" / "dotnet-app"

        mock_run.return_value = Mock(
            returncode=1, stdout="", stderr="Error: build failed"
        )

        # Act
        from code_indexer.scip.indexers.csharp import CSharpIndexer

        indexer = CSharpIndexer()
        result = indexer.generate(project_dir, output_dir, "solution")

        # Assert
        assert result.is_failure()
        assert result.exit_code == 1
        assert "build failed" in result.stderr

    def test_csharp_solution_fails_when_no_sln_file(self, tmp_path):
        """Test C# solution indexing fails when .sln file missing."""
        # Arrange
        project_dir = tmp_path / "dotnet-app"
        project_dir.mkdir()
        # NO .sln file created - empty directory
        output_dir = tmp_path / ".code-indexer" / "scip" / "dotnet-app"

        # Act
        from code_indexer.scip.indexers.csharp import CSharpIndexer

        indexer = CSharpIndexer()
        result = indexer.generate(project_dir, output_dir, "solution")

        # Assert
        assert result.is_failure()
        assert result.exit_code == -1
        assert "No .sln file found" in result.stderr

    @patch("code_indexer.scip.indexers.csharp.shutil.which")
    def test_csharp_indexer_is_available_true(self, mock_which):
        """Test scip-dotnet availability when installed."""
        # Arrange
        mock_which.return_value = "/usr/local/bin/scip-dotnet"

        # Act
        from code_indexer.scip.indexers.csharp import CSharpIndexer

        indexer = CSharpIndexer()
        result = indexer.is_available()

        # Assert
        assert result is True
        mock_which.assert_called_once_with("scip-dotnet")

    @patch("code_indexer.scip.indexers.csharp.shutil.which")
    def test_csharp_indexer_is_available_false(self, mock_which):
        """Test scip-dotnet availability when not installed."""
        # Arrange
        mock_which.return_value = None

        # Act
        from code_indexer.scip.indexers.csharp import CSharpIndexer

        indexer = CSharpIndexer()
        result = indexer.is_available()

        # Assert
        assert result is False
        mock_which.assert_called_once_with("scip-dotnet")

    @patch("subprocess.run")
    def test_csharp_indexer_get_version(self, mock_run):
        """Test getting scip-dotnet version."""
        # Arrange
        mock_run.return_value = Mock(returncode=0, stdout="1.0.0\n", stderr="")

        # Act
        from code_indexer.scip.indexers.csharp import CSharpIndexer

        indexer = CSharpIndexer()
        version = indexer.get_version()

        # Assert
        assert version == "1.0.0"
        mock_run.assert_called_once()


class TestGoIndexer:
    """Test Go/scip-go indexer."""

    @patch("code_indexer.scip.indexers.go.shutil.move")
    @patch("subprocess.run")
    def test_go_indexing_success(self, mock_run, mock_move, tmp_path):
        """Test successful Go module project indexing."""
        # Arrange
        project_dir = tmp_path / "go-service"
        project_dir.mkdir()
        (project_dir / "go.mod").write_text("module github.com/example/service")

        # Create mock .scip file
        scip_file = project_dir / "index.scip"
        scip_file.write_text("mock scip data")

        output_dir = tmp_path / ".code-indexer" / "scip" / "go-service"

        mock_run.return_value = Mock(returncode=0, stdout="Indexed", stderr="")

        # Act
        indexer = GoIndexer()
        result = indexer.generate(project_dir, output_dir, "module")

        # Assert
        assert result.is_success()
        assert result.exit_code == 0
        assert mock_run.called
        assert mock_move.called
        args = mock_run.call_args[0][0]
        assert "scip-go" in args

    @patch("subprocess.run")
    def test_go_indexing_failure(self, mock_run, tmp_path):
        """Test failed Go project indexing."""
        # Arrange
        project_dir = tmp_path / "go-service"
        project_dir.mkdir()
        (project_dir / "go.mod").write_text("module github.com/example/service")
        output_dir = tmp_path / ".code-indexer" / "scip" / "go-service"

        mock_run.return_value = Mock(
            returncode=1, stdout="", stderr="Error: build failed"
        )

        # Act
        indexer = GoIndexer()
        result = indexer.generate(project_dir, output_dir, "module")

        # Assert
        assert result.is_failure()
        assert result.exit_code == 1
        assert "build failed" in result.stderr

    @patch("code_indexer.scip.indexers.go.shutil.which")
    def test_go_indexer_is_available_true(self, mock_which):
        """Test scip-go availability when installed."""
        # Arrange
        mock_which.return_value = "/usr/local/bin/scip-go"

        # Act
        indexer = GoIndexer()
        result = indexer.is_available()

        # Assert
        assert result is True
        mock_which.assert_called_once_with("scip-go")

    @patch("code_indexer.scip.indexers.go.shutil.which")
    def test_go_indexer_is_available_false(self, mock_which):
        """Test scip-go availability when not installed."""
        # Arrange
        mock_which.return_value = None

        # Act
        indexer = GoIndexer()
        result = indexer.is_available()

        # Assert
        assert result is False
        mock_which.assert_called_once_with("scip-go")

    @patch("subprocess.run")
    def test_go_indexer_get_version(self, mock_run):
        """Test getting scip-go version."""
        # Arrange
        mock_run.return_value = Mock(returncode=0, stdout="v0.3.0\n", stderr="")

        # Act
        indexer = GoIndexer()
        version = indexer.get_version()

        # Assert
        assert version == "v0.3.0"
        mock_run.assert_called_once()

    def test_go_indexer_no_go_mod(self, tmp_path):
        """Test Go indexing when go.mod file missing."""
        # Arrange
        project_dir = tmp_path / "go-service"
        project_dir.mkdir()
        output_dir = tmp_path / ".code-indexer" / "scip" / "go-service"

        # Act
        indexer = GoIndexer()
        result = indexer.generate(project_dir, output_dir, "module")

        # Assert
        assert result.is_failure()
        assert result.exit_code == -1
        assert "No go.mod file found" in result.stderr

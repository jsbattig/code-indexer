"""Unit tests for SCIP indexers."""

from pathlib import Path
from unittest.mock import Mock, patch
from code_indexer.scip.indexers.base import IndexerResult, IndexerStatus
from code_indexer.scip.indexers.java import JavaIndexer
from code_indexer.scip.indexers.typescript import TypeScriptIndexer
from code_indexer.scip.indexers.python import PythonIndexer


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

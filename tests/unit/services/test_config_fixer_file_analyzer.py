"""
Unit tests for ConfigFixer FileSystemAnalyzer.

Tests verify correct usage of FileIdentifier for analyzing project files.
"""

from unittest.mock import Mock, patch, MagicMock
from code_indexer.services.config_fixer import FileSystemAnalyzer
from code_indexer.config import Config


class TestFileSystemAnalyzer:
    """Test FileSystemAnalyzer.analyze_project_files() method."""

    def test_analyze_project_files_uses_file_identifier(self, tmp_path):
        """Verify that analyze_project_files uses FileIdentifier correctly."""
        # Create a mock config
        config = Mock(spec=Config)
        codebase_dir = tmp_path / "test_project"
        codebase_dir.mkdir()

        # Create some test files
        (codebase_dir / "test.py").write_text("print('hello')")
        (codebase_dir / "test2.py").write_text("print('world')")

        # Mock FileIdentifier to verify it's called correctly
        # Note: Import is inside method, so we mock it at the file_identifier module level
        with patch(
            "code_indexer.services.file_identifier.FileIdentifier"
        ) as mock_file_identifier:
            # Setup mock to return expected data structure
            mock_instance = MagicMock()
            mock_file_identifier.return_value = mock_instance
            mock_instance.get_current_files.return_value = {
                "test.py": {"file_path": "test.py", "file_hash": "abc123"},
                "test2.py": {"file_path": "test2.py", "file_hash": "def456"},
            }

            # Call the method under test
            result = FileSystemAnalyzer.analyze_project_files(codebase_dir, config)

            # Verify FileIdentifier was instantiated with correct parameters
            mock_file_identifier.assert_called_once_with(codebase_dir, config)

            # Verify get_current_files() was called (not get_indexable_files())
            mock_instance.get_current_files.assert_called_once()

            # Verify the result has the expected structure
            assert "total_files_to_index" in result
            assert result["total_files_to_index"] == 2
            assert "discovered_files" in result
            assert len(result["discovered_files"]) == 2

    def test_analyze_project_files_returns_correct_structure(self, tmp_path):
        """Verify analyze_project_files returns the expected dictionary structure."""
        config = Mock(spec=Config)
        codebase_dir = tmp_path / "test_project"
        codebase_dir.mkdir()

        # Create test files with different extensions
        (codebase_dir / "file1.py").write_text("# python")
        (codebase_dir / "file2.js").write_text("// javascript")
        (codebase_dir / "file3.md").write_text("# markdown")

        with patch(
            "code_indexer.services.file_identifier.FileIdentifier"
        ) as mock_file_identifier:
            mock_instance = MagicMock()
            mock_file_identifier.return_value = mock_instance
            mock_instance.get_current_files.return_value = {
                "file1.py": {"file_path": "file1.py"},
                "file2.js": {"file_path": "file2.js"},
                "file3.md": {"file_path": "file3.md"},
            }

            result = FileSystemAnalyzer.analyze_project_files(codebase_dir, config)

            # Verify all required keys exist
            assert "total_files_to_index" in result
            assert "discovered_files" in result
            assert "file_extensions_found" in result

            # Verify correct counts
            assert result["total_files_to_index"] == 3
            assert len(result["discovered_files"]) == 3

            # Verify file extensions are extracted
            extensions = result["file_extensions_found"]
            assert isinstance(extensions, list)
            assert set(extensions) == {"py", "js", "md"}

    def test_analyze_project_files_handles_empty_directory(self, tmp_path):
        """Verify analyze_project_files handles directory with no indexable files."""
        config = Mock(spec=Config)
        codebase_dir = tmp_path / "empty_project"
        codebase_dir.mkdir()

        with patch(
            "code_indexer.services.file_identifier.FileIdentifier"
        ) as mock_file_identifier:
            mock_instance = MagicMock()
            mock_file_identifier.return_value = mock_instance
            mock_instance.get_current_files.return_value = {}

            result = FileSystemAnalyzer.analyze_project_files(codebase_dir, config)

            assert result["total_files_to_index"] == 0
            assert result["discovered_files"] == []
            assert result["file_extensions_found"] == []

    def test_analyze_project_files_handles_exceptions_gracefully(self, tmp_path):
        """Verify analyze_project_files returns safe defaults on exceptions."""
        config = Mock(spec=Config)
        codebase_dir = tmp_path / "test_project"
        codebase_dir.mkdir()

        with patch(
            "code_indexer.services.file_identifier.FileIdentifier"
        ) as mock_file_identifier:
            # Simulate an exception during file identification
            mock_file_identifier.side_effect = Exception("File system error")

            result = FileSystemAnalyzer.analyze_project_files(codebase_dir, config)

            # Should return safe defaults on error
            assert result["total_files_to_index"] == 0
            assert result["discovered_files"] == []
            assert result["file_extensions_found"] == []

    def test_analyze_project_files_extracts_file_paths_correctly(self, tmp_path):
        """Verify analyze_project_files extracts file paths from get_current_files() result."""
        config = Mock(spec=Config)
        codebase_dir = tmp_path / "test_project"
        codebase_dir.mkdir()

        with patch(
            "code_indexer.services.file_identifier.FileIdentifier"
        ) as mock_file_identifier:
            mock_instance = MagicMock()
            mock_file_identifier.return_value = mock_instance

            # get_current_files() returns Dict[str, Dict[str, Any]]
            # Keys are file paths (strings), values are metadata dicts
            mock_instance.get_current_files.return_value = {
                "src/main.py": {"file_hash": "hash1"},
                "tests/test_main.py": {"file_hash": "hash2"},
                "README.md": {"file_hash": "hash3"},
            }

            result = FileSystemAnalyzer.analyze_project_files(codebase_dir, config)

            # Verify file paths are extracted from dictionary keys
            discovered = result["discovered_files"]
            assert len(discovered) == 3
            assert "src/main.py" in discovered
            assert "tests/test_main.py" in discovered
            assert "README.md" in discovered

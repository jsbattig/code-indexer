"""
Tests for TestReorganizer class that implements test directory reorganization.

This test suite validates the reorganization of test files from a flat structure
into logical directory hierarchies based on test type and functionality.
"""

import os
import shutil
from pathlib import Path
from unittest.mock import patch
import pytest

from code_indexer.test_infrastructure.test_reorganizer import TestFileReorganizer


class TestTestReorganizer:
    """Tests for TestReorganizer functionality."""

    def setup_method(self):
        """Set up test environment with temporary directories."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.test_root = Path(self.temp_dir) / "tests"
        self.test_root.mkdir()
        
        # Create sample test files that represent the current structure
        self.sample_files = [
            "test_python_semantic_parser.py",
            "test_java_semantic_parser.py", 
            "test_chunker.py",
            "test_semantic_chunker.py",
            "test_config.py",
            "test_cancellation_handling.py",
            "test_cancellation_integration.py",
            "test_qdrant_service_config_integration.py",
            "test_docker_manager.py",
            "test_cli_flag_validation.py",
            "test_git_aware_processor.py",
            "test_infrastructure.py",
            "test_parallel_voyage_performance.py",
            "test_claude_e2e.py",
            "test_end_to_end_complete.py",
            "test_reconcile_comprehensive_e2e.py",
            "test_git_workflows_e2e.py",
            "test_payload_indexes_focused_e2e.py",
            "test_semantic_search_capabilities_e2e.py",
        ]
        
        # Create the test files
        for filename in self.sample_files:
            test_file = self.test_root / filename
            test_file.write_text(f'"""Test file: {filename}"""\nimport pytest\n\ndef test_sample():\n    assert True\n')

    def teardown_method(self):
        """Clean up temporary directories."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_reorganizer_initialization(self):
        """Test TestReorganizer initializes with correct parameters."""
        reorganizer = TestFileReorganizer(self.test_root)
        
        assert reorganizer.test_root == self.test_root
        assert reorganizer.dry_run is False
        assert reorganizer.backup_original is True

    def test_categorize_unit_tests(self):
        """Test categorization of unit tests by functionality."""
        reorganizer = TestFileReorganizer(self.test_root)
        
        # These should be categorized as unit tests in parsers subdirectory
        parser_tests = reorganizer.categorize_test_file("test_python_semantic_parser.py")
        assert parser_tests["category"] == "unit"
        assert parser_tests["subcategory"] == "parsers"
        
        # These should be categorized as unit tests in chunking subdirectory 
        chunking_tests = reorganizer.categorize_test_file("test_chunker.py")
        assert chunking_tests["category"] == "unit"
        assert chunking_tests["subcategory"] == "chunking"
        
        # Config tests should be in config subdirectory
        config_tests = reorganizer.categorize_test_file("test_config.py")
        assert config_tests["category"] == "unit"
        assert config_tests["subcategory"] == "config"

    def test_categorize_integration_tests(self):
        """Test categorization of integration tests."""
        reorganizer = TestFileReorganizer(self.test_root)
        
        # Service integration tests
        service_tests = reorganizer.categorize_test_file("test_qdrant_service_config_integration.py")
        assert service_tests["category"] == "integration"
        assert service_tests["subcategory"] == "services"
        
        # Docker integration tests
        docker_tests = reorganizer.categorize_test_file("test_docker_manager.py")
        assert docker_tests["category"] == "integration"
        assert docker_tests["subcategory"] == "docker"
        
        # Performance tests
        perf_tests = reorganizer.categorize_test_file("test_parallel_voyage_performance.py")
        assert perf_tests["category"] == "integration"
        assert perf_tests["subcategory"] == "performance"

    def test_categorize_e2e_tests(self):
        """Test categorization of end-to-end tests."""
        reorganizer = TestFileReorganizer(self.test_root)
        
        # Claude integration e2e tests
        claude_tests = reorganizer.categorize_test_file("test_claude_e2e.py")
        assert claude_tests["category"] == "e2e"
        assert claude_tests["subcategory"] == "claude_integration"
        
        # General e2e tests should go to misc
        general_e2e = reorganizer.categorize_test_file("test_end_to_end_complete.py")
        assert general_e2e["category"] == "e2e"
        assert general_e2e["subcategory"] == "misc"
        
        # Git workflow tests
        git_tests = reorganizer.categorize_test_file("test_reconcile_comprehensive_e2e.py")
        assert git_tests["category"] == "e2e"
        assert git_tests["subcategory"] == "git_workflows"
        
        # Payload index tests
        payload_tests = reorganizer.categorize_test_file("test_payload_indexes_focused_e2e.py")
        assert payload_tests["category"] == "e2e"
        assert payload_tests["subcategory"] == "payload_indexes"
        
        # Semantic search tests
        search_tests = reorganizer.categorize_test_file("test_semantic_search_capabilities_e2e.py")
        assert search_tests["category"] == "e2e"
        assert search_tests["subcategory"] == "semantic_search"

    def test_create_directory_structure(self):
        """Test creation of the new directory structure."""
        reorganizer = TestFileReorganizer(self.test_root)
        
        reorganizer.create_directory_structure()
        
        # Check that main categories are created
        assert (self.test_root / "unit").exists()
        assert (self.test_root / "integration").exists()
        assert (self.test_root / "e2e").exists()
        assert (self.test_root / "shared").exists()
        assert (self.test_root / "fixtures").exists()
        
        # Check unit test subdirectories
        assert (self.test_root / "unit" / "parsers").exists()
        assert (self.test_root / "unit" / "chunking").exists()
        assert (self.test_root / "unit" / "config").exists()
        assert (self.test_root / "unit" / "cancellation").exists()
        assert (self.test_root / "unit" / "services").exists()
        assert (self.test_root / "unit" / "cli").exists()
        assert (self.test_root / "unit" / "git").exists()
        assert (self.test_root / "unit" / "infrastructure").exists()
        assert (self.test_root / "unit" / "bugfixes").exists()
        
        # Check integration test subdirectories
        assert (self.test_root / "integration" / "performance").exists()
        assert (self.test_root / "integration" / "docker").exists()
        assert (self.test_root / "integration" / "multiproject").exists()
        assert (self.test_root / "integration" / "indexing").exists()
        assert (self.test_root / "integration" / "cli").exists()
        assert (self.test_root / "integration" / "services").exists()
        
        # Check e2e test subdirectories
        assert (self.test_root / "e2e" / "git_workflows").exists()
        assert (self.test_root / "e2e" / "payload_indexes").exists()
        assert (self.test_root / "e2e" / "providers").exists()
        assert (self.test_root / "e2e" / "semantic_search").exists()
        assert (self.test_root / "e2e" / "claude_integration").exists()
        assert (self.test_root / "e2e" / "infrastructure").exists()
        assert (self.test_root / "e2e" / "display").exists()
        assert (self.test_root / "e2e" / "misc").exists()

    def test_move_files_dry_run(self):
        """Test moving files in dry run mode."""
        reorganizer = TestFileReorganizer(self.test_root, dry_run=True)
        reorganizer.create_directory_structure()
        
        move_plan = reorganizer.reorganize_tests()
        
        # Verify files are planned to be moved but not actually moved
        assert len(move_plan) == len(self.sample_files)
        
        # Files should still be in original location
        for filename in self.sample_files:
            assert (self.test_root / filename).exists()
        
        # Verify move plan contains correct categorizations
        parser_moves = [item for item in move_plan if "parser" in item["source"]]
        assert len(parser_moves) == 2  # python and java parser tests
        
        for move in parser_moves:
            assert move["destination"].startswith("unit/parsers/")

    def test_move_files_actual(self):
        """Test actual file moving without dry run."""
        reorganizer = TestFileReorganizer(self.test_root, dry_run=False)
        reorganizer.create_directory_structure()
        
        reorganizer.reorganize_tests()
        
        # Verify files have been moved to correct locations
        assert not (self.test_root / "test_python_semantic_parser.py").exists()
        assert (self.test_root / "unit" / "parsers" / "test_python_semantic_parser.py").exists()
        
        assert not (self.test_root / "test_chunker.py").exists()
        assert (self.test_root / "unit" / "chunking" / "test_chunker.py").exists()
        
        assert not (self.test_root / "test_config.py").exists()
        assert (self.test_root / "unit" / "config" / "test_config.py").exists()
        
        assert not (self.test_root / "test_claude_e2e.py").exists()
        assert (self.test_root / "e2e" / "claude_integration" / "test_claude_e2e.py").exists()

    def test_update_import_paths(self):
        """Test updating import paths in moved test files."""
        reorganizer = TestFileReorganizer(self.test_root, dry_run=False)
        
        # Create a test file with imports that need updating
        test_file = self.test_root / "test_sample_with_imports.py"
        test_content = '''"""Test file with imports."""
import pytest
from ...conftest import some_fixture
from ...shared_utilities import helper_function
from ...e2e_test_setup import setup_e2e

def test_sample():
    assert True
'''
        test_file.write_text(test_content)
        
        reorganizer.create_directory_structure()
        
        # Move the file to unit/parsers
        dest_file = self.test_root / "unit" / "parsers" / "test_sample_with_imports.py"
        shutil.move(str(test_file), str(dest_file))
        
        # Update import paths
        reorganizer.update_import_paths(dest_file, "unit/parsers")
        
        updated_content = dest_file.read_text()
        
        # Verify imports have been updated with correct relative paths
        assert "from ...conftest import some_fixture" in updated_content
        assert "from ...shared_utilities import helper_function" in updated_content
        assert "from ...e2e_test_setup import setup_e2e" in updated_content

    def test_backup_original_structure(self):
        """Test backup of original test structure.""" 
        reorganizer = TestFileReorganizer(self.test_root, backup_original=True)
        
        backup_path = reorganizer.create_backup()
        
        assert backup_path.exists()
        assert backup_path.name.startswith("tests_backup_")
        
        # Verify all original files are in backup
        for filename in self.sample_files:
            assert (backup_path / filename).exists()

    def test_validation_after_reorganization(self):
        """Test validation that all tests can still be discovered and run."""
        reorganizer = TestFileReorganizer(self.test_root, dry_run=False)
        reorganizer.create_directory_structure()
        reorganizer.reorganize_tests()
        
        validation_results = reorganizer.validate_reorganization()
        
        assert validation_results["all_files_moved"] is True
        assert validation_results["no_missing_files"] is True
        assert validation_results["import_paths_valid"] is True
        assert len(validation_results["discovered_tests"]) == len(self.sample_files)

    def test_get_file_statistics(self):
        """Test getting statistics about file categorization."""
        reorganizer = TestFileReorganizer(self.test_root)
        
        stats = reorganizer.get_file_statistics()
        
        assert "unit" in stats
        assert "integration" in stats
        assert "e2e" in stats
        assert stats["total"] == len(self.sample_files)
        
        # Verify counts match expected categorization
        assert stats["unit"] > 0
        assert stats["integration"] > 0 
        assert stats["e2e"] > 0

    def test_error_handling_invalid_test_root(self):
        """Test error handling when test root doesn't exist."""
        invalid_path = Path("/nonexistent/path")
        
        with pytest.raises(FileNotFoundError):
            TestFileReorganizer(invalid_path)

    def test_error_handling_permission_denied(self):
        """Test error handling when unable to create directories due to permissions."""
        reorganizer = TestFileReorganizer(self.test_root)
        
        # Mock Path.mkdir to raise PermissionError
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied")):
            with pytest.raises(PermissionError):
                reorganizer.create_directory_structure()

    def test_rollback_functionality(self):
        """Test rollback functionality in case of errors during reorganization."""
        reorganizer = TestFileReorganizer(self.test_root, backup_original=True)
        backup_path = reorganizer.create_backup()
        
        reorganizer.create_directory_structure()
        
        # Simulate an error during reorganization
        with patch.object(reorganizer, 'reorganize_tests', side_effect=Exception("Simulated error")):
            with pytest.raises(Exception):
                reorganizer.reorganize_tests()
        
        # Test rollback
        reorganizer.rollback_from_backup(backup_path)
        
        # Verify original files are restored
        for filename in self.sample_files:
            assert (self.test_root / filename).exists()
"""Tests for configuration fixer functionality."""

import json
import shutil
from pathlib import Path
import uuid
from unittest.mock import Mock, patch

import pytest

from .conftest import get_local_tmp_dir

from code_indexer.services.json_validator import JSONSyntaxValidator, JSONSyntaxRepairer
from code_indexer.services.config_fixer import (
    ConfigurationValidator,
    ConfigurationRepairer,
    GitStateDetector,
    CollectionAnalyzer,
    generate_fix_report,
)
from code_indexer.config import Config


class TestJSONSyntaxValidator:
    """Test JSON syntax validation and repair."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.validator = JSONSyntaxValidator()

    def teardown_method(self):
        """Cleanup test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_valid_json_passes_validation(self):
        """Test that valid JSON passes validation."""
        valid_json = {"key1": "value1", "key2": {"nested": "value"}, "key3": [1, 2, 3]}

        json_file = self.temp_dir / "valid.json"
        with open(json_file, "w") as f:
            json.dump(valid_json, f, indent=2)

        result = self.validator.validate_json_file(json_file)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.fixes) == 0

    def test_trailing_comma_detection(self):
        """Test detection of trailing commas."""
        invalid_json = """
        {
            "key1": "value1",
            "key2": "value2",
        }
        """

        json_file = self.temp_dir / "trailing_comma.json"
        json_file.write_text(invalid_json)

        result = self.validator.validate_json_file(json_file)

        assert result.valid is False
        assert len(result.fixes) > 0
        assert any(fix.fix_type == "trailing_comma" for fix in result.fixes)

    def test_unquoted_keys_detection(self):
        """Test detection of unquoted keys."""
        invalid_json = """
        {
            key1: "value1",
            "key2": "value2"
        }
        """

        json_file = self.temp_dir / "unquoted_keys.json"
        json_file.write_text(invalid_json)

        result = self.validator.validate_json_file(json_file)

        assert result.valid is False
        assert len(result.fixes) > 0
        assert any(fix.fix_type == "unquoted_key" for fix in result.fixes)

    def test_single_quotes_detection(self):
        """Test detection of single quotes."""
        invalid_json = """
        {
            'key1': 'value1',
            "key2": "value2"
        }
        """

        json_file = self.temp_dir / "single_quotes.json"
        json_file.write_text(invalid_json)

        result = self.validator.validate_json_file(json_file)

        assert result.valid is False
        assert len(result.fixes) > 0
        assert any(fix.fix_type == "single_quotes" for fix in result.fixes)

    def test_comments_detection(self):
        """Test detection of JavaScript-style comments."""
        invalid_json = """
        {
            // This is a comment
            "key1": "value1",
            "key2": "value2" /* Block comment */
        }
        """

        json_file = self.temp_dir / "comments.json"
        json_file.write_text(invalid_json)

        result = self.validator.validate_json_file(json_file)

        assert result.valid is False
        assert len(result.fixes) > 0
        assert any(
            fix.fix_type in ["line_comment", "block_comment"] for fix in result.fixes
        )


class TestJSONSyntaxRepairer:
    """Test JSON syntax repair functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.repairer = JSONSyntaxRepairer()

    def teardown_method(self):
        """Cleanup test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_automatic_repair_of_trailing_commas(self):
        """Test automatic repair of trailing commas."""
        invalid_json = """
        {
            "key1": "value1",
            "key2": "value2",
        }
        """

        json_file = self.temp_dir / "trailing_comma.json"
        json_file.write_text(invalid_json)

        result = self.repairer.repair_json_file(json_file, dry_run=False)

        assert result["success"] is True
        assert len(result["fixes_applied"]) > 0

        # Verify the file is now valid JSON
        with open(json_file, "r") as f:
            repaired_data = json.load(f)

        assert repaired_data["key1"] == "value1"
        assert repaired_data["key2"] == "value2"

    def test_dry_run_mode(self):
        """Test that dry run mode doesn't modify files."""
        invalid_json = """
        {
            "key1": "value1",
            "key2": "value2",
        }
        """

        json_file = self.temp_dir / "dry_run_test.json"
        json_file.write_text(invalid_json)
        original_content = json_file.read_text()

        result = self.repairer.repair_json_file(json_file, dry_run=True)

        assert result["success"] is True
        assert json_file.read_text() == original_content  # File unchanged

    def test_backup_creation(self):
        """Test that backups are created when repairing."""
        invalid_json = """
        {
            "key1": "value1",
            "key2": "value2",
        }
        """

        json_file = self.temp_dir / "backup_test.json"
        json_file.write_text(invalid_json)

        result = self.repairer.repair_json_file(
            json_file, dry_run=False, create_backup=True
        )

        assert result["success"] is True
        assert result["backup_created"] is not None

        backup_file = Path(result["backup_created"])
        assert backup_file.exists()
        assert backup_file.read_text() == invalid_json


class TestGitStateDetector:
    """Test git state detection functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Cleanup test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_non_git_directory(self):
        """Test detection in non-git directory."""
        git_state = GitStateDetector.detect_git_state(self.temp_dir)

        assert git_state["git_available"] is False
        assert git_state["current_branch"] == "unknown"
        assert git_state["current_commit"] == "unknown"

    @patch("subprocess.run")
    def test_git_directory_detection(self, mock_run):
        """Test detection in git directory."""
        # Mock git commands
        mock_results = [
            Mock(returncode=0, stdout="true"),  # is-inside-work-tree
            Mock(returncode=0, stdout="main"),  # branch name
            Mock(returncode=0, stdout="abc1234"),  # commit hash
            Mock(returncode=0, stdout=""),  # status (clean)
        ]
        mock_run.side_effect = mock_results

        git_state = GitStateDetector.detect_git_state(self.temp_dir)

        assert git_state["git_available"] is True
        assert git_state["current_branch"] == "main"
        assert git_state["current_commit"] == "abc1234"
        assert git_state["is_dirty"] is False


class TestConfigurationValidator:
    """Test configuration validation functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.validator = ConfigurationValidator(self.config_dir)

    def teardown_method(self):
        """Cleanup test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_correct_codebase_dir_detection(self):
        """Test detection of correct codebase directory."""
        correct_dir = self.validator.detect_correct_codebase_dir()
        assert correct_dir == self.temp_dir

    def test_correct_project_name_detection(self):
        """Test detection of correct project name."""
        project_name = self.validator.detect_correct_project_name()
        assert project_name == self.temp_dir.name

    def test_config_validation_with_wrong_path(self):
        """Test config validation detects wrong paths."""
        config = Config(codebase_dir="/wrong/path")

        fixes = self.validator.validate_config(config)

        assert len(fixes) > 0
        assert any(fix.fix_type == "path_correction" for fix in fixes)

    def test_config_validation_with_tilde_path(self):
        """Test config validation handles tilde paths."""
        config = Config(codebase_dir="~/some/path")

        fixes = self.validator.validate_config(config)

        assert len(fixes) > 0
        assert any(fix.fix_type == "path_correction" for fix in fixes)

    def test_metadata_validation_with_wrong_project_id(self):
        """Test metadata validation detects wrong project ID."""
        config = Config(codebase_dir=self.temp_dir)
        metadata = {"project_id": "wrong-project-name"}

        fixes = self.validator.validate_metadata(metadata, config)

        assert len(fixes) > 0
        assert any(fix.fix_type == "project_name_correction" for fix in fixes)

    def test_metadata_validation_with_invalid_file_paths(self):
        """Test metadata validation detects invalid file paths."""
        config = Config(codebase_dir=self.temp_dir)
        metadata = {
            "project_id": self.temp_dir.name,
            "files_to_index": [
                str(get_local_tmp_dir() / "nonexistent/file.py"),
                "/another/invalid/path.js",
            ],
        }

        fixes = self.validator.validate_metadata(metadata, config)

        assert len(fixes) > 0
        assert any(fix.fix_type == "invalid_file_paths" for fix in fixes)


class TestCollectionAnalyzer:
    """Test Qdrant collection analysis functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_qdrant_client = Mock()
        self.analyzer = CollectionAnalyzer(self.mock_qdrant_client)

    def test_derive_stats_from_empty_collection(self):
        """Test stats derivation from empty collection."""
        # Mock collection exists and has no points
        self.mock_qdrant_client.collection_exists.return_value = True
        self.mock_qdrant_client.get_collection_info.return_value = {"points_count": 0}

        stats = self.analyzer.derive_stats_from_collection("test_collection")

        assert stats is not None
        assert stats["files_processed"] == 0
        assert stats["chunks_indexed"] == 0
        assert stats["status"] == "needs_indexing"

    def test_derive_stats_from_populated_collection(self):
        """Test stats derivation from collection with data."""
        # Mock collection exists and has points
        self.mock_qdrant_client.collection_exists.return_value = True
        self.mock_qdrant_client.get_collection_info.return_value = {"points_count": 50}

        stats = self.analyzer.derive_stats_from_collection("test_collection")

        assert stats is not None
        assert stats["files_processed"] == 5  # max(1, 50 // 10) = 5
        assert stats["chunks_indexed"] == 50
        assert stats["status"] == "completed"

    def test_find_wrong_collections(self):
        """Test finding collections with wrong project names."""
        # This test should verify the method works as expected
        # Since the actual implementation prints a note and returns empty list,
        # we test that behavior
        wrong_collections = self.analyzer.find_wrong_collections("correct-project")

        # Current implementation returns empty list with a note
        assert wrong_collections == []


class TestConfigurationRepairer:
    """Test configuration repair functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Create test config files
        self.config_file = self.config_dir / "config.json"
        self.metadata_file = self.config_dir / "metadata.json"

        # Create basic config
        test_config = {
            "codebase_dir": "~/wrong/path",
            "embedding_provider": "voyage-ai",
            "qdrant": {"host": "http://localhost:6333"},
        }

        with open(self.config_file, "w") as f:
            json.dump(test_config, f, indent=2)

        # Create test metadata with corruption
        test_metadata = {
            "project_id": "test-codebase",
            "git_available": False,
            "current_branch": "unknown",
            "current_commit": "unknown",
            "files_to_index": [str(get_local_tmp_dir() / "nonexistent/file.py")],
            "files_processed": 0,
            "chunks_indexed": 0,
        }

        with open(self.metadata_file, "w") as f:
            json.dump(test_metadata, f, indent=2)

        self.repairer = ConfigurationRepairer(self.config_dir, dry_run=True)

    def teardown_method(self):
        """Cleanup test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("code_indexer.services.config_fixer.GitStateDetector.detect_git_state")
    def test_fix_configuration_dry_run(self, mock_git_state):
        """Test configuration fix in dry run mode."""
        # Mock git state
        mock_git_state.return_value = {
            "git_available": True,
            "current_branch": "main",
            "current_commit": "abc1234",
            "is_dirty": False,
        }

        result = self.repairer.fix_configuration()

        assert result.success is True
        assert len(result.fixes_applied) > 0

        # Verify fixes include expected corrections
        fix_types = [fix.fix_type for fix in result.fixes_applied]
        assert "path_correction" in fix_types
        assert "project_name_correction" in fix_types

    def test_json_syntax_error_handling(self):
        """Test handling of JSON syntax errors."""
        # Create invalid JSON with a simple trailing comma that the repairer can handle
        invalid_json = '{"codebase_dir": "~/wrong/path",}'
        self.config_file.write_text(invalid_json)

        result = self.repairer.fix_configuration()

        # JSON repair should succeed, but config loading will fail due to missing required fields
        # The test should expect this behavior - JSON repair succeeds but config validation fails
        assert result.success is False
        assert any("Could not load configuration" in error for error in result.errors)

    @patch("code_indexer.services.config_fixer.QdrantClient")
    def test_collection_analysis_integration(self, mock_qdrant_class):
        """Test integration with collection analysis."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_qdrant_class.return_value = mock_client

        result = self.repairer.fix_configuration()

        assert result.success is True
        # The current implementation does not check for wrong collections
        # since collection listing is not implemented, so no warnings expected
        assert len(result.warnings) == 0


class TestEndToEndScenarios:
    """Test realistic end-to-end scenarios."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Cleanup test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_typical_test_corruption_scenario(self):
        """Test fixing typical corruption from test runs."""
        # Create corrupted config similar to what tests create
        corrupted_config = {
            "codebase_dir": str(
                get_local_tmp_dir() / "tmp12345/test_dir"
            ),  # Temp directory
            "embedding_provider": "voyage-ai",
            "qdrant": {"host": "http://localhost:6333"},
        }

        corrupted_metadata = {
            "project_id": "test-codebase",  # Wrong project name
            "git_available": False,  # Wrong git state
            "current_branch": "unknown",
            "current_commit": "unknown",
            "files_to_index": [
                str(
                    get_local_tmp_dir() / "tmp12345/test_dir/file1.py"
                ),  # Invalid paths
                str(get_local_tmp_dir() / "tmp12345/test_dir/file2.py"),
            ],
            "files_processed": 0,
            "chunks_indexed": 0,
            "status": "completed",  # Inconsistent with files_processed
        }

        config_file = self.config_dir / "config.json"
        metadata_file = self.config_dir / "metadata.json"

        with open(config_file, "w") as f:
            json.dump(corrupted_config, f, indent=2)

        with open(metadata_file, "w") as f:
            json.dump(corrupted_metadata, f, indent=2)

        # Create some actual project files
        (self.temp_dir / "main.py").write_text("# Main file")
        (self.temp_dir / "utils.py").write_text("# Utilities")

        repairer = ConfigurationRepairer(self.config_dir, dry_run=True)

        with patch(
            "code_indexer.services.config_fixer.GitStateDetector.detect_git_state"
        ) as mock_git:
            mock_git.return_value = {
                "git_available": True,
                "current_branch": "main",
                "current_commit": "abc1234",
                "is_dirty": False,
            }

            result = repairer.fix_configuration()

        assert result.success is True
        assert (
            len(result.fixes_applied) >= 4
        )  # Path, project name, git state, file paths

        # Verify the types of fixes applied
        fix_types = [fix.fix_type for fix in result.fixes_applied]
        expected_fixes = [
            "path_correction",
            "project_name_correction",
            "git_availability_correction",
            "invalid_file_paths",
        ]

        for expected_fix in expected_fixes:
            assert expected_fix in fix_types, f"Missing expected fix: {expected_fix}"


class TestFixReportGeneration:
    """Test fix report generation."""

    def test_successful_fix_report(self):
        """Test report generation for successful fixes."""
        from code_indexer.services.config_fixer import FixResult, ConfigFix

        fixes = [
            ConfigFix(
                fix_type="path_correction",
                field="codebase_dir",
                description="Fix codebase directory path",
                old_value=str(get_local_tmp_dir() / "wrong"),
                new_value="/correct/path",
                reason="Path correction needed",
            ),
            ConfigFix(
                fix_type="project_name_correction",
                field="project_id",
                description="Fix project name",
                old_value="test-codebase",
                new_value="actual-project",
                reason="Project name should match directory",
            ),
        ]

        result = FixResult(
            success=True, fixes_applied=fixes, errors=[], warnings=["Sample warning"]
        )

        report = generate_fix_report(result, dry_run=False)

        assert "Configuration fix completed successfully" in report
        assert "Applied 2 fixes" in report
        assert "Path Correction" in report
        assert "Project Name Correction" in report
        assert "1 warnings" in report

    def test_dry_run_report(self):
        """Test report generation for dry run mode."""
        from code_indexer.services.config_fixer import FixResult, ConfigFix

        fixes = [
            ConfigFix(
                fix_type="path_correction",
                field="codebase_dir",
                description="Fix codebase directory path",
                old_value=str(get_local_tmp_dir() / "wrong"),
                new_value="/correct/path",
                reason="Path correction needed",
            )
        ]

        result = FixResult(success=True, fixes_applied=fixes, errors=[], warnings=[])

        report = generate_fix_report(result, dry_run=True)

        assert "simulation" in report
        assert "Would apply 1 fixes" in report

    def test_error_report(self):
        """Test report generation for failed fixes."""
        from code_indexer.services.config_fixer import FixResult

        result = FixResult(
            success=False,
            fixes_applied=[],
            errors=["Critical error occurred", "Another error"],
            warnings=[],
        )

        report = generate_fix_report(result, dry_run=False)

        assert "Configuration fix failed" in report
        assert "Critical error occurred" in report
        assert "Another error" in report


class TestProjectConfigurationFixes:
    """Test project configuration fixes for CoW clones."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.temp_dir / ".code-indexer"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.metadata_file = self.config_dir / "metadata.json"

    def teardown_method(self):
        """Cleanup test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("code_indexer.services.config_fixer.DockerManager")
    def test_regenerate_project_configuration(self, mock_docker_manager_class):
        """Test project configuration regeneration for CoW clones."""
        # Mock DockerManager
        mock_docker_manager = Mock()
        mock_docker_manager._generate_container_names.return_value = {
            "project_hash": "abc12345",
            "qdrant_name": "cidx-abc12345-qdrant",
            "ollama_name": "cidx-abc12345-ollama",
            "data_cleaner_name": "cidx-abc12345-data-cleaner",
        }
        mock_docker_manager.allocate_project_ports.return_value = {
            "qdrant_port": 6833,
            "ollama_port": 11934,
            "data_cleaner_port": 8591,
        }
        mock_docker_manager_class.return_value = mock_docker_manager

        # Create a basic config for testing
        config_data = {
            "codebase_dir": str(self.temp_dir),
            "embedding_provider": "voyage-ai",
            "voyage_ai": {"model": "voyage-code-2"},
            "qdrant": {"collection_base_name": "test-collection"},
            "project_ports": {
                "qdrant_port": 6333,
                "ollama_port": 11434,
                "data_cleaner_port": 8091,
            },
        }

        with open(self.config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        repairer = ConfigurationRepairer(self.config_dir, dry_run=True)

        # Test the project configuration regeneration
        project_info = repairer._regenerate_project_configuration()

        assert project_info["project_hash"] == "abc12345"
        assert project_info["container_names"]["qdrant_name"] == "cidx-abc12345-qdrant"
        assert project_info["port_assignments"]["qdrant_port"] == 6833

    @patch("code_indexer.services.config_fixer.DockerManager")
    @patch("code_indexer.services.config_fixer.ConfigManager")
    def test_fix_project_configuration_integration(
        self, mock_config_manager_class, mock_docker_manager_class
    ):
        """Test the complete project configuration fix integration."""
        # Mock DockerManager
        mock_docker_manager = Mock()
        mock_docker_manager._generate_container_names.return_value = {
            "project_hash": "def67890",
            "qdrant_name": "cidx-def67890-qdrant",
            "ollama_name": "cidx-def67890-ollama",
            "data_cleaner_name": "cidx-def67890-data-cleaner",
        }
        mock_docker_manager.allocate_project_ports.return_value = {
            "qdrant_port": 7333,
            "ollama_port": 12434,
            "data_cleaner_port": 9091,
        }
        mock_docker_manager_class.return_value = mock_docker_manager

        # Mock ConfigManager
        mock_config_manager = Mock()
        mock_config = Mock()
        mock_config.project_ports = Mock()
        mock_config.project_ports.qdrant_port = 6333  # Old port
        mock_config.project_ports.ollama_port = 11434  # Old port
        mock_config.project_ports.data_cleaner_port = 8091  # Old port
        mock_config_manager.load.return_value = mock_config
        mock_config_manager_class.return_value = mock_config_manager

        repairer = ConfigurationRepairer(self.config_dir, dry_run=True)

        # Test the complete fix flow
        fixes = repairer._fix_project_configuration()

        # Should detect port differences and suggest fixes
        assert len(fixes) > 0
        fix_types = [fix.fix_type for fix in fixes]
        assert "port_regeneration" in fix_types
        assert "container_name_regeneration" in fix_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

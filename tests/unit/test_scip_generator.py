"""Unit tests for SCIP generator orchestration."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from code_indexer.scip.generator import SCIPGenerator, GenerationResult
from code_indexer.scip.discovery import DiscoveredProject
from code_indexer.scip.indexers.base import IndexerResult, IndexerStatus


class TestSCIPGenerator:
    """Test SCIP generation orchestration."""
    
    def test_generator_initialization(self, tmp_path):
        """Test generator can be initialized with repo root."""
        generator = SCIPGenerator(tmp_path)
        assert generator.repo_root == tmp_path
        assert generator.scip_dir == tmp_path / ".code-indexer" / "scip"
    
    @patch('code_indexer.scip.generator.ProjectDiscovery')
    @patch('code_indexer.scip.generator.JavaIndexer')
    def test_generate_single_project_success(self, mock_java_indexer, mock_discovery, tmp_path):
        """Test successful generation for single Java project."""
        # Arrange
        project = DiscoveredProject(
            relative_path=Path("backend"),
            language="java",
            build_system="maven",
            build_file=Path("backend/pom.xml")
        )
        
        mock_discovery_instance = Mock()
        mock_discovery_instance.discover.return_value = [project]
        mock_discovery.return_value = mock_discovery_instance
        
        mock_indexer_instance = Mock()
        mock_indexer_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0
        )
        mock_java_indexer.return_value = mock_indexer_instance
        
        # Act
        generator = SCIPGenerator(tmp_path)
        result = generator.generate()
        
        # Assert
        assert result.total_projects == 1
        assert result.successful_projects == 1
        assert result.failed_projects == 0
        assert result.is_complete_success()
    
    @patch('code_indexer.scip.generator.ProjectDiscovery')
    @patch('code_indexer.scip.generator.JavaIndexer')
    @patch('code_indexer.scip.generator.TypeScriptIndexer')
    def test_generate_multiple_projects_partial_success(
        self, mock_ts_indexer, mock_java_indexer, mock_discovery, tmp_path
    ):
        """Test partial success with multiple projects."""
        # Arrange
        projects = [
            DiscoveredProject(
                relative_path=Path("backend"),
                language="java",
                build_system="maven",
                build_file=Path("backend/pom.xml")
            ),
            DiscoveredProject(
                relative_path=Path("frontend"),
                language="typescript",
                build_system="npm",
                build_file=Path("frontend/package.json")
            )
        ]
        
        mock_discovery_instance = Mock()
        mock_discovery_instance.discover.return_value = projects
        mock_discovery.return_value = mock_discovery_instance
        
        # Java succeeds
        mock_java_instance = Mock()
        mock_java_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0
        )
        mock_java_indexer.return_value = mock_java_instance
        
        # TypeScript fails
        mock_ts_instance = Mock()
        mock_ts_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.FAILED,
            duration_seconds=1.0,
            output_file=None,
            stdout="",
            stderr="Error: npm install failed",
            exit_code=1
        )
        mock_ts_indexer.return_value = mock_ts_instance
        
        # Act
        generator = SCIPGenerator(tmp_path)
        result = generator.generate()
        
        # Assert
        assert result.total_projects == 2
        assert result.successful_projects == 1
        assert result.failed_projects == 1
        assert result.is_partial_success()
        assert not result.is_complete_success()
        assert not result.is_complete_failure()
    
    @patch('code_indexer.scip.generator.ProjectDiscovery')
    def test_generate_no_projects_found(self, mock_discovery, tmp_path):
        """Test generation when no projects are discovered."""
        # Arrange
        mock_discovery_instance = Mock()
        mock_discovery_instance.discover.return_value = []
        mock_discovery.return_value = mock_discovery_instance
        
        # Act
        generator = SCIPGenerator(tmp_path)
        result = generator.generate()
        
        # Assert
        assert result.total_projects == 0
        assert result.successful_projects == 0
        assert result.failed_projects == 0
    
    @patch('code_indexer.scip.generator.ProjectDiscovery')
    @patch('code_indexer.scip.generator.PythonIndexer')
    def test_generate_with_progress_callback(self, mock_python_indexer, mock_discovery, tmp_path):
        """Test progress reporting during generation."""
        # Arrange
        project = DiscoveredProject(
            relative_path=Path("python-lib"),
            language="python",
            build_system="poetry",
            build_file=Path("python-lib/pyproject.toml")
        )
        
        mock_discovery_instance = Mock()
        mock_discovery_instance.discover.return_value = [project]
        mock_discovery.return_value = mock_discovery_instance
        
        mock_indexer_instance = Mock()
        mock_indexer_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=1.5,
            output_file=tmp_path / ".code-indexer" / "scip" / "python-lib" / "index.scip",
            stdout="Done",
            stderr="",
            exit_code=0
        )
        mock_python_indexer.return_value = mock_indexer_instance
        
        progress_callback = Mock()
        
        # Act
        generator = SCIPGenerator(tmp_path)
        result = generator.generate(progress_callback=progress_callback)
        
        # Assert
        assert progress_callback.called
        assert result.successful_projects == 1


class TestSCIPRebuild:
    """Test SCIP rebuild functionality for targeted regeneration."""

    @patch('code_indexer.scip.status.StatusTracker')
    @patch('code_indexer.scip.generator.JavaIndexer')
    def test_rebuild_single_project_success(self, mock_java_indexer, mock_status_tracker, tmp_path):
        """Test rebuilding a single failed project successfully."""
        from code_indexer.scip.status import GenerationStatus, ProjectStatus, OverallStatus

        # Arrange - Create mock status with one failed project
        backend_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="java",
            build_system="maven",
            timestamp="2025-01-01T00:00:00",
            error_message="Build failed",
            exit_code=1
        )

        frontend_status = ProjectStatus(
            status=OverallStatus.SUCCESS,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            duration_seconds=2.0,
            output_file=str(tmp_path / ".code-indexer" / "scip" / "frontend" / "index.scip")
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.LIMBO,
            total_projects=2,
            successful_projects=1,
            failed_projects=1,
            projects={
                "backend": backend_status,
                "frontend": frontend_status
            }
        )

        mock_tracker_instance = Mock()
        mock_tracker_instance.load.return_value = mock_status
        mock_status_tracker.return_value = mock_tracker_instance

        # Mock successful rebuild
        mock_indexer_instance = Mock()
        mock_indexer_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=3.0,
            output_file=tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0
        )
        mock_java_indexer.return_value = mock_indexer_instance

        # Act
        generator = SCIPGenerator(tmp_path)
        rebuild_result = generator.rebuild_projects(project_paths=["backend"])

        # Assert
        assert "backend" in rebuild_result
        assert rebuild_result["backend"].status == OverallStatus.SUCCESS
        assert rebuild_result["backend"].duration_seconds == 3.0
        assert mock_indexer_instance.generate.called
        # Frontend should NOT be regenerated
        assert "frontend" not in rebuild_result

    @patch('code_indexer.scip.status.StatusTracker')
    @patch('code_indexer.scip.generator.JavaIndexer')
    @patch('code_indexer.scip.generator.TypeScriptIndexer')
    def test_rebuild_failed_only_flag(self, mock_ts_indexer, mock_java_indexer, mock_status_tracker, tmp_path):
        """Test --failed flag rebuilds only failed projects."""
        from code_indexer.scip.status import GenerationStatus, ProjectStatus, OverallStatus

        # Arrange - Two failed, one successful
        backend_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="java",
            build_system="maven",
            timestamp="2025-01-01T00:00:00",
            error_message="Build failed",
            exit_code=1
        )

        frontend_status = ProjectStatus(
            status=OverallStatus.SUCCESS,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            duration_seconds=2.0,
            output_file=str(tmp_path / ".code-indexer" / "scip" / "frontend" / "index.scip")
        )

        api_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            error_message="npm install failed",
            exit_code=1
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.LIMBO,
            total_projects=3,
            successful_projects=1,
            failed_projects=2,
            projects={
                "backend": backend_status,
                "frontend": frontend_status,
                "api": api_status
            }
        )

        mock_tracker_instance = Mock()
        mock_tracker_instance.load.return_value = mock_status
        mock_status_tracker.return_value = mock_tracker_instance

        # Mock successful rebuilds
        mock_java_instance = Mock()
        mock_java_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=3.0,
            output_file=tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0
        )
        mock_java_indexer.return_value = mock_java_instance

        mock_ts_instance = Mock()
        mock_ts_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=tmp_path / ".code-indexer" / "scip" / "api" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0
        )
        mock_ts_indexer.return_value = mock_ts_instance

        # Act
        generator = SCIPGenerator(tmp_path)
        rebuild_result = generator.rebuild_projects(project_paths=[], failed_only=True)

        # Assert
        assert len(rebuild_result) == 2
        assert "backend" in rebuild_result
        assert "api" in rebuild_result
        assert "frontend" not in rebuild_result  # Successful project not rebuilt
        assert rebuild_result["backend"].status == OverallStatus.SUCCESS
        assert rebuild_result["api"].status == OverallStatus.SUCCESS

    @patch('code_indexer.scip.status.StatusTracker')
    @patch('code_indexer.scip.generator.TypeScriptIndexer')
    def test_rebuild_force_flag_on_successful_project(self, mock_ts_indexer, mock_status_tracker, tmp_path):
        """Test --force flag allows rebuilding successful projects."""
        from code_indexer.scip.status import GenerationStatus, ProjectStatus, OverallStatus

        # Arrange - All successful
        frontend_status = ProjectStatus(
            status=OverallStatus.SUCCESS,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            duration_seconds=2.0,
            output_file=str(tmp_path / ".code-indexer" / "scip" / "frontend" / "index.scip")
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.SUCCESS,
            total_projects=1,
            successful_projects=1,
            failed_projects=0,
            projects={"frontend": frontend_status}
        )

        mock_tracker_instance = Mock()
        mock_tracker_instance.load.return_value = mock_status
        mock_status_tracker.return_value = mock_tracker_instance

        # Mock rebuild
        mock_ts_instance = Mock()
        mock_ts_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.2,
            output_file=tmp_path / ".code-indexer" / "scip" / "frontend" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0
        )
        mock_ts_indexer.return_value = mock_ts_instance

        # Act - Without force, should skip
        generator = SCIPGenerator(tmp_path)
        rebuild_result = generator.rebuild_projects(project_paths=["frontend"], force=False)

        # Assert - Not rebuilt
        assert len(rebuild_result) == 0
        assert not mock_ts_instance.generate.called

        # Act - With force, should rebuild
        rebuild_result = generator.rebuild_projects(project_paths=["frontend"], force=True)

        # Assert - Rebuilt
        assert len(rebuild_result) == 1
        assert "frontend" in rebuild_result
        assert rebuild_result["frontend"].status == OverallStatus.SUCCESS
        assert rebuild_result["frontend"].duration_seconds == 2.2
        assert mock_ts_instance.generate.called

    @patch('code_indexer.scip.status.StatusTracker')
    @patch('code_indexer.scip.generator.JavaIndexer')
    @patch('code_indexer.scip.generator.TypeScriptIndexer')
    def test_rebuild_multiple_projects(self, mock_ts_indexer, mock_java_indexer, mock_status_tracker, tmp_path):
        """Test rebuilding multiple specific projects."""
        from code_indexer.scip.status import GenerationStatus, ProjectStatus, OverallStatus

        # Arrange - Multiple failed projects
        backend_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="java",
            build_system="maven",
            timestamp="2025-01-01T00:00:00",
            error_message="Build failed",
            exit_code=1
        )

        api_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            error_message="npm install failed",
            exit_code=1
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.FAILED,
            total_projects=2,
            successful_projects=0,
            failed_projects=2,
            projects={
                "backend": backend_status,
                "api": api_status
            }
        )

        mock_tracker_instance = Mock()
        mock_tracker_instance.load.return_value = mock_status
        mock_status_tracker.return_value = mock_tracker_instance

        # Mock successful rebuilds
        mock_java_instance = Mock()
        mock_java_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=3.0,
            output_file=tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0
        )
        mock_java_indexer.return_value = mock_java_instance

        mock_ts_instance = Mock()
        mock_ts_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=tmp_path / ".code-indexer" / "scip" / "api" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0
        )
        mock_ts_indexer.return_value = mock_ts_instance

        # Act
        generator = SCIPGenerator(tmp_path)
        rebuild_result = generator.rebuild_projects(project_paths=["backend", "api"])

        # Assert
        assert len(rebuild_result) == 2
        assert "backend" in rebuild_result
        assert "api" in rebuild_result
        assert rebuild_result["backend"].status == OverallStatus.SUCCESS
        assert rebuild_result["api"].status == OverallStatus.SUCCESS
        # Verify overall status transitioned to SUCCESS
        saved_status = mock_tracker_instance.save.call_args[0][0]
        assert saved_status.overall_status == OverallStatus.SUCCESS

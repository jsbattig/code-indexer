"""Unit tests for SCIP generator orchestration."""

import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch
from code_indexer.scip.generator import SCIPGenerator
from code_indexer.scip.discovery import DiscoveredProject
from code_indexer.scip.indexers.base import IndexerResult, IndexerStatus


class TestSCIPGenerator:
    """Test SCIP generation orchestration."""

    def _create_test_scip_file(self, scip_file_path):
        """Create a minimal valid SCIP protobuf for testing."""
        from code_indexer.scip.protobuf import scip_pb2

        scip_file_path.parent.mkdir(parents=True, exist_ok=True)

        index = scip_pb2.Index()
        doc = index.documents.add()
        doc.relative_path = "Main.java"
        doc.language = "java"

        symbol_info = doc.symbols.add()
        symbol_info.symbol = "com/example/Main#"
        symbol_info.display_name = "Main"

        occ = doc.occurrences.add()
        occ.symbol = "com/example/Main#"
        occ.symbol_roles = 1
        occ.range.extend([0, 0, 0, 10])

        scip_file_path.write_bytes(index.SerializeToString())
        return scip_file_path

    def _assert_database_has_required_tables(self, db_path):
        """Assert database exists and has required tables with data."""
        assert db_path.exists(), f"Database file should exist at {db_path}"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            assert "symbols" in tables, "Database should have symbols table"
            assert "occurrences" in tables, "Database should have occurrences table"
            assert "documents" in tables, "Database should have documents table"
            assert "call_graph" in tables, "Database should have call_graph table"

            cursor.execute("SELECT COUNT(*) FROM symbols")
            symbol_count = cursor.fetchone()[0]
            assert symbol_count > 0, "Symbols table should contain data"

            cursor.execute("SELECT COUNT(*) FROM documents")
            doc_count = cursor.fetchone()[0]
            assert doc_count > 0, "Documents table should contain data"

    def test_generator_initialization(self, tmp_path):
        """Test generator can be initialized with repo root."""
        generator = SCIPGenerator(tmp_path)
        assert generator.repo_root == tmp_path
        assert generator.scip_dir == tmp_path / ".code-indexer" / "scip"

    @patch("code_indexer.scip.generator.DatabaseManager")
    @patch("code_indexer.scip.generator.SCIPDatabaseBuilder")
    @patch("code_indexer.scip.generator.ProjectDiscovery")
    @patch("code_indexer.scip.generator.JavaIndexer")
    def test_generate_single_project_success(
        self, mock_java_indexer, mock_discovery, mock_builder, mock_db_manager, tmp_path
    ):
        """Test successful generation for single Java project."""
        # Arrange
        project = DiscoveredProject(
            relative_path=Path("backend"),
            language="java",
            build_system="maven",
            build_file=Path("backend/pom.xml"),
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
            exit_code=0,
        )
        mock_java_indexer.return_value = mock_indexer_instance

        # Mock database building
        mock_db_manager_instance = Mock()
        mock_db_manager.return_value = mock_db_manager_instance
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance

        # Act
        generator = SCIPGenerator(tmp_path)
        result = generator.generate()

        # Assert
        assert result.total_projects == 1
        assert result.successful_projects == 1
        assert result.failed_projects == 0
        assert result.is_complete_success()

    @patch("code_indexer.scip.generator.DatabaseManager")
    @patch("code_indexer.scip.generator.SCIPDatabaseBuilder")
    @patch("code_indexer.scip.generator.ProjectDiscovery")
    @patch("code_indexer.scip.generator.JavaIndexer")
    @patch("code_indexer.scip.generator.TypeScriptIndexer")
    def test_generate_multiple_projects_partial_success(
        self,
        mock_ts_indexer,
        mock_java_indexer,
        mock_discovery,
        mock_builder,
        mock_db_manager,
        tmp_path,
    ):
        """Test partial success with multiple projects."""
        # Arrange
        projects = [
            DiscoveredProject(
                relative_path=Path("backend"),
                language="java",
                build_system="maven",
                build_file=Path("backend/pom.xml"),
            ),
            DiscoveredProject(
                relative_path=Path("frontend"),
                language="typescript",
                build_system="npm",
                build_file=Path("frontend/package.json"),
            ),
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
            exit_code=0,
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
            exit_code=1,
        )
        mock_ts_indexer.return_value = mock_ts_instance

        # Mock database building
        mock_db_manager_instance = Mock()
        mock_db_manager.return_value = mock_db_manager_instance
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance

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

    @patch("code_indexer.scip.generator.ProjectDiscovery")
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

    @patch("code_indexer.scip.generator.DatabaseManager")
    @patch("code_indexer.scip.generator.SCIPDatabaseBuilder")
    @patch("code_indexer.scip.generator.ProjectDiscovery")
    @patch("code_indexer.scip.generator.PythonIndexer")
    def test_generate_with_progress_callback(
        self,
        mock_python_indexer,
        mock_discovery,
        mock_builder,
        mock_db_manager,
        tmp_path,
    ):
        """Test progress reporting during generation."""
        # Arrange
        project = DiscoveredProject(
            relative_path=Path("python-lib"),
            language="python",
            build_system="poetry",
            build_file=Path("python-lib/pyproject.toml"),
        )

        mock_discovery_instance = Mock()
        mock_discovery_instance.discover.return_value = [project]
        mock_discovery.return_value = mock_discovery_instance

        mock_indexer_instance = Mock()
        mock_indexer_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=1.5,
            output_file=tmp_path
            / ".code-indexer"
            / "scip"
            / "python-lib"
            / "index.scip",
            stdout="Done",
            stderr="",
            exit_code=0,
        )
        mock_python_indexer.return_value = mock_indexer_instance

        # Mock database building
        mock_db_manager_instance = Mock()
        mock_db_manager.return_value = mock_db_manager_instance
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance

        progress_callback = Mock()

        # Act
        generator = SCIPGenerator(tmp_path)
        result = generator.generate(progress_callback=progress_callback)

        # Assert
        assert progress_callback.called
        assert result.successful_projects == 1

    @patch("code_indexer.scip.generator.ProjectDiscovery")
    @patch("code_indexer.scip.generator.JavaIndexer")
    def test_generate_creates_database_alongside_protobuf(
        self, mock_java_indexer, mock_discovery, tmp_path
    ):
        """Test that generator creates .scip.db database after successful protobuf generation."""
        # Arrange
        scip_file = tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip"
        self._create_test_scip_file(scip_file)

        project = DiscoveredProject(
            relative_path=Path("backend"),
            language="java",
            build_system="maven",
            build_file=Path("backend/pom.xml"),
        )

        mock_discovery_instance = Mock()
        mock_discovery_instance.discover.return_value = [project]
        mock_discovery.return_value = mock_discovery_instance

        mock_indexer_instance = Mock()
        mock_indexer_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=scip_file,
            stdout="Success",
            stderr="",
            exit_code=0,
        )
        mock_java_indexer.return_value = mock_indexer_instance

        # Act
        generator = SCIPGenerator(tmp_path)
        result = generator.generate()

        # Assert
        db_file = scip_file.with_suffix(".scip.db")
        self._assert_database_has_required_tables(db_file)
        assert result.successful_projects == 1

    @patch("code_indexer.scip.generator.ProjectDiscovery")
    @patch("code_indexer.scip.generator.JavaIndexer")
    @patch("code_indexer.scip.generator.DatabaseManager")
    def test_database_build_failure_marks_generation_as_failed(
        self, mock_db_manager, mock_java_indexer, mock_discovery, tmp_path
    ):
        """Test that database build failure causes generation to fail (Anti-Fallback principle).

        Per Anti-Fallback Foundation #2: "We value graceful failure over forceful success."
        Database is the PRIMARY deliverable - if it fails, generation must fail.
        """
        # Arrange
        scip_file = tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip"
        self._create_test_scip_file(scip_file)

        project = DiscoveredProject(
            relative_path=Path("backend"),
            language="java",
            build_system="maven",
            build_file=Path("backend/pom.xml"),
        )

        mock_discovery_instance = Mock()
        mock_discovery_instance.discover.return_value = [project]
        mock_discovery.return_value = mock_discovery_instance

        # Indexer succeeds (protobuf generated)
        mock_indexer_instance = Mock()
        mock_indexer_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=scip_file,
            stdout="Success",
            stderr="",
            exit_code=0,
        )
        mock_java_indexer.return_value = mock_indexer_instance

        # Database build fails
        mock_db_manager_instance = Mock()
        mock_db_manager_instance.create_schema.side_effect = Exception("Disk full")
        mock_db_manager.return_value = mock_db_manager_instance

        # Act
        generator = SCIPGenerator(tmp_path)
        result = generator.generate()

        # Assert - Generation MUST fail when database build fails
        assert (
            result.failed_projects == 1
        ), "Database build failure must mark generation as failed"
        assert (
            result.successful_projects == 0
        ), "No projects should be marked successful when database fails"
        assert result.is_complete_failure(), "Overall result must be complete failure"

        # Verify the project result status is FAILED
        assert len(result.project_results) == 1
        project_result = result.project_results[0]
        assert project_result.indexer_result.status == IndexerStatus.FAILED
        assert "Database build failed" in project_result.indexer_result.stderr

    @patch("code_indexer.scip.generator.ProjectDiscovery")
    @patch("code_indexer.scip.generator.JavaIndexer")
    def test_generate_deletes_existing_database(
        self, mock_java_indexer, mock_discovery, tmp_path
    ):
        """Test that generating twice creates clean database on second run (no stale data).

        Critical Issue #2: Running cidx scip generate twice without cleaning may append to
        existing database, leaving stale data. DatabaseManager must delete existing .scip.db
        before creating new database to ensure clean slate.
        """
        # Arrange
        scip_file = tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip"
        db_file = scip_file.with_suffix(".scip.db")

        project = DiscoveredProject(
            relative_path=Path("backend"),
            language="java",
            build_system="maven",
            build_file=Path("backend/pom.xml"),
        )

        mock_discovery_instance = Mock()
        mock_discovery_instance.discover.return_value = [project]
        mock_discovery.return_value = mock_discovery_instance

        # First generation
        scip_file_v1 = self._create_test_scip_file(scip_file)
        mock_indexer_instance = Mock()
        mock_indexer_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=scip_file_v1,
            stdout="Success",
            stderr="",
            exit_code=0,
        )
        mock_java_indexer.return_value = mock_indexer_instance

        generator = SCIPGenerator(tmp_path)
        result1 = generator.generate()
        assert result1.successful_projects == 1

        # Verify first database exists and has data
        assert db_file.exists()
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM symbols")
            count_v1 = cursor.fetchone()[0]
            assert count_v1 > 0, "First generation should populate database"

        # Second generation with DIFFERENT data (more symbols)
        from code_indexer.scip.protobuf import scip_pb2

        index = scip_pb2.Index()
        doc = index.documents.add()
        doc.relative_path = "Main.java"
        doc.language = "java"

        # Add 2 symbols instead of 1
        for i in range(2):
            symbol_info = doc.symbols.add()
            symbol_info.symbol = f"com/example/Class{i}#"
            symbol_info.display_name = f"Class{i}"

            occ = doc.occurrences.add()
            occ.symbol = f"com/example/Class{i}#"
            occ.symbol_roles = 1
            occ.range.extend([i, 0, i, 10])

        scip_file.write_bytes(index.SerializeToString())

        result2 = generator.generate()
        assert result2.successful_projects == 1

        # Verify second database has ONLY new data (not appended)
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM symbols")
            count_v2 = cursor.fetchone()[0]

            # Should have exactly 2 symbols (new data only), not 3 (old + new)
            assert (
                count_v2 == 2
            ), f"Database should have clean data (2 symbols), found {count_v2}. Stale data detected!"


class TestSCIPRebuild:
    """Test SCIP rebuild functionality for targeted regeneration."""

    @patch("code_indexer.scip.generator.DatabaseManager")
    @patch("code_indexer.scip.generator.SCIPDatabaseBuilder")
    @patch("code_indexer.scip.status.StatusTracker")
    @patch("code_indexer.scip.generator.JavaIndexer")
    def test_rebuild_single_project_success(
        self,
        mock_java_indexer,
        mock_status_tracker,
        mock_builder,
        mock_db_manager,
        tmp_path,
    ):
        """Test rebuilding a single failed project successfully."""
        from code_indexer.scip.status import (
            GenerationStatus,
            ProjectStatus,
            OverallStatus,
        )

        # Arrange - Create mock status with one failed project
        backend_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="java",
            build_system="maven",
            timestamp="2025-01-01T00:00:00",
            error_message="Build failed",
            exit_code=1,
        )

        frontend_status = ProjectStatus(
            status=OverallStatus.SUCCESS,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            duration_seconds=2.0,
            output_file=str(
                tmp_path / ".code-indexer" / "scip" / "frontend" / "index.scip"
            ),
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.LIMBO,
            total_projects=2,
            successful_projects=1,
            failed_projects=1,
            projects={"backend": backend_status, "frontend": frontend_status},
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
            exit_code=0,
        )
        mock_java_indexer.return_value = mock_indexer_instance

        # Mock database building
        mock_db_manager_instance = Mock()
        mock_db_manager.return_value = mock_db_manager_instance
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance

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

    @patch("code_indexer.scip.generator.DatabaseManager")
    @patch("code_indexer.scip.generator.SCIPDatabaseBuilder")
    @patch("code_indexer.scip.status.StatusTracker")
    @patch("code_indexer.scip.generator.JavaIndexer")
    @patch("code_indexer.scip.generator.TypeScriptIndexer")
    def test_rebuild_failed_only_flag(
        self,
        mock_ts_indexer,
        mock_java_indexer,
        mock_status_tracker,
        mock_builder,
        mock_db_manager,
        tmp_path,
    ):
        """Test --failed flag rebuilds only failed projects."""
        from code_indexer.scip.status import (
            GenerationStatus,
            ProjectStatus,
            OverallStatus,
        )

        # Arrange - Two failed, one successful
        backend_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="java",
            build_system="maven",
            timestamp="2025-01-01T00:00:00",
            error_message="Build failed",
            exit_code=1,
        )

        frontend_status = ProjectStatus(
            status=OverallStatus.SUCCESS,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            duration_seconds=2.0,
            output_file=str(
                tmp_path / ".code-indexer" / "scip" / "frontend" / "index.scip"
            ),
        )

        api_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            error_message="npm install failed",
            exit_code=1,
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.LIMBO,
            total_projects=3,
            successful_projects=1,
            failed_projects=2,
            projects={
                "backend": backend_status,
                "frontend": frontend_status,
                "api": api_status,
            },
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
            exit_code=0,
        )
        mock_java_indexer.return_value = mock_java_instance

        mock_ts_instance = Mock()
        mock_ts_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=tmp_path / ".code-indexer" / "scip" / "api" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0,
        )
        mock_ts_indexer.return_value = mock_ts_instance

        # Mock database building
        mock_db_manager_instance = Mock()
        mock_db_manager.return_value = mock_db_manager_instance
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance

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

    @patch("code_indexer.scip.generator.DatabaseManager")
    @patch("code_indexer.scip.generator.SCIPDatabaseBuilder")
    @patch("code_indexer.scip.status.StatusTracker")
    @patch("code_indexer.scip.generator.TypeScriptIndexer")
    def test_rebuild_force_flag_on_successful_project(
        self,
        mock_ts_indexer,
        mock_status_tracker,
        mock_builder,
        mock_db_manager,
        tmp_path,
    ):
        """Test --force flag allows rebuilding successful projects."""
        from code_indexer.scip.status import (
            GenerationStatus,
            ProjectStatus,
            OverallStatus,
        )

        # Arrange - All successful
        frontend_status = ProjectStatus(
            status=OverallStatus.SUCCESS,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            duration_seconds=2.0,
            output_file=str(
                tmp_path / ".code-indexer" / "scip" / "frontend" / "index.scip"
            ),
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.SUCCESS,
            total_projects=1,
            successful_projects=1,
            failed_projects=0,
            projects={"frontend": frontend_status},
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
            exit_code=0,
        )
        mock_ts_indexer.return_value = mock_ts_instance

        # Mock database building
        mock_db_manager_instance = Mock()
        mock_db_manager.return_value = mock_db_manager_instance
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance

        # Act - Without force, should skip
        generator = SCIPGenerator(tmp_path)
        rebuild_result = generator.rebuild_projects(
            project_paths=["frontend"], force=False
        )

        # Assert - Not rebuilt
        assert len(rebuild_result) == 0
        assert not mock_ts_instance.generate.called

        # Act - With force, should rebuild
        rebuild_result = generator.rebuild_projects(
            project_paths=["frontend"], force=True
        )

        # Assert - Rebuilt
        assert len(rebuild_result) == 1
        assert "frontend" in rebuild_result
        assert rebuild_result["frontend"].status == OverallStatus.SUCCESS
        assert rebuild_result["frontend"].duration_seconds == 2.2
        assert mock_ts_instance.generate.called

    @patch("code_indexer.scip.generator.DatabaseManager")
    @patch("code_indexer.scip.generator.SCIPDatabaseBuilder")
    @patch("code_indexer.scip.status.StatusTracker")
    @patch("code_indexer.scip.generator.JavaIndexer")
    @patch("code_indexer.scip.generator.TypeScriptIndexer")
    def test_rebuild_multiple_projects(
        self,
        mock_ts_indexer,
        mock_java_indexer,
        mock_status_tracker,
        mock_builder,
        mock_db_manager,
        tmp_path,
    ):
        """Test rebuilding multiple specific projects."""
        from code_indexer.scip.status import (
            GenerationStatus,
            ProjectStatus,
            OverallStatus,
        )

        # Arrange - Multiple failed projects
        backend_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="java",
            build_system="maven",
            timestamp="2025-01-01T00:00:00",
            error_message="Build failed",
            exit_code=1,
        )

        api_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="typescript",
            build_system="npm",
            timestamp="2025-01-01T00:00:00",
            error_message="npm install failed",
            exit_code=1,
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.FAILED,
            total_projects=2,
            successful_projects=0,
            failed_projects=2,
            projects={"backend": backend_status, "api": api_status},
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
            exit_code=0,
        )
        mock_java_indexer.return_value = mock_java_instance

        mock_ts_instance = Mock()
        mock_ts_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=2.5,
            output_file=tmp_path / ".code-indexer" / "scip" / "api" / "index.scip",
            stdout="Success",
            stderr="",
            exit_code=0,
        )
        mock_ts_indexer.return_value = mock_ts_instance

        # Mock database building
        mock_db_manager_instance = Mock()
        mock_db_manager.return_value = mock_db_manager_instance
        mock_builder_instance = Mock()
        mock_builder.return_value = mock_builder_instance

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

    @patch("code_indexer.scip.status.StatusTracker")
    @patch("code_indexer.scip.generator.JavaIndexer")
    @patch("code_indexer.scip.generator.DatabaseManager")
    def test_rebuild_database_build_failure_marks_rebuild_as_failed(
        self, mock_db_manager, mock_java_indexer, mock_status_tracker, tmp_path
    ):
        """Test that database build failure during rebuild causes rebuild to fail (Anti-Fallback).

        Per Anti-Fallback Foundation #2: "We value graceful failure over forceful success."
        Database is the PRIMARY deliverable - if it fails during rebuild, rebuild must fail.
        """
        from code_indexer.scip.status import (
            GenerationStatus,
            ProjectStatus,
            OverallStatus,
        )

        # Arrange - Failed project to rebuild
        backend_status = ProjectStatus(
            status=OverallStatus.FAILED,
            language="java",
            build_system="maven",
            timestamp="2025-01-01T00:00:00",
            error_message="Build failed",
            exit_code=1,
        )

        mock_status = GenerationStatus(
            overall_status=OverallStatus.FAILED,
            total_projects=1,
            successful_projects=0,
            failed_projects=1,
            projects={"backend": backend_status},
        )

        mock_tracker_instance = Mock()
        mock_tracker_instance.load.return_value = mock_status
        mock_status_tracker.return_value = mock_tracker_instance

        # Indexer succeeds (protobuf generated)
        scip_file = tmp_path / ".code-indexer" / "scip" / "backend" / "index.scip"
        mock_indexer_instance = Mock()
        mock_indexer_instance.generate.return_value = IndexerResult(
            status=IndexerStatus.SUCCESS,
            duration_seconds=3.0,
            output_file=scip_file,
            stdout="Success",
            stderr="",
            exit_code=0,
        )
        mock_java_indexer.return_value = mock_indexer_instance

        # Database build fails
        mock_db_manager_instance = Mock()
        mock_db_manager_instance.create_schema.side_effect = Exception("Disk full")
        mock_db_manager.return_value = mock_db_manager_instance

        # Act
        generator = SCIPGenerator(tmp_path)
        rebuild_result = generator.rebuild_projects(project_paths=["backend"])

        # Assert - Rebuild MUST fail when database build fails
        assert len(rebuild_result) == 1
        assert "backend" in rebuild_result
        assert (
            rebuild_result["backend"].status == OverallStatus.FAILED
        ), "Database build failure must mark rebuild as failed"
        assert "Database build failed" in rebuild_result["backend"].error_message

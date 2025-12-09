"""Integration tests for SCIP functionality."""

import pytest
from pathlib import Path
from code_indexer.scip.discovery import ProjectDiscovery
from code_indexer.scip.generator import SCIPGenerator
from code_indexer.scip.status import StatusTracker, OverallStatus


class TestSCIPIntegration:
    """Integration tests for end-to-end SCIP workflows."""
    
    def test_discover_and_report_projects(self, tmp_path):
        """Test project discovery in a real repository structure."""
        # Create sample repository
        (tmp_path / "backend" / "pom.xml").parent.mkdir(parents=True)
        (tmp_path / "backend" / "pom.xml").write_text("<project></project>")
        
        (tmp_path / "frontend" / "package.json").parent.mkdir(parents=True)
        (tmp_path / "frontend" / "package.json").write_text('{"name": "test"}')
        
        # Discover projects
        discovery = ProjectDiscovery(tmp_path)
        projects = discovery.discover()
        
        # Verify discovery
        assert len(projects) == 2
        project_paths = {str(p.relative_path) for p in projects}
        assert "backend" in project_paths
        assert "frontend" in project_paths
    
    def test_generator_creates_status_file(self, tmp_path):
        """Test that generator creates status.json file."""
        # Create sample repository with no projects
        (tmp_path / "README.md").write_text("# Test Repo")
        
        # Run generator (will find no projects)
        generator = SCIPGenerator(tmp_path)
        result = generator.generate()
        
        # Verify result
        assert result.total_projects == 0
        assert result.successful_projects == 0
    
    def test_status_persistence(self, tmp_path):
        """Test status tracking persistence."""
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        
        # Create and save status
        tracker = StatusTracker(scip_dir)
        from code_indexer.scip.status import GenerationStatus, ProjectStatus
        from datetime import datetime
        
        status = GenerationStatus(
            overall_status=OverallStatus.SUCCESS,
            total_projects=1,
            successful_projects=1,
            failed_projects=0,
            projects={
                "backend": ProjectStatus(
                    status=OverallStatus.SUCCESS,
                    language="java",
                    build_system="maven",
                    duration_seconds=2.5,
                    output_file="backend/index.scip",
                    timestamp=datetime.now().isoformat()
                )
            }
        )
        
        tracker.save(status)
        
        # Load and verify
        loaded = tracker.load()
        assert loaded.overall_status == OverallStatus.SUCCESS
        assert loaded.total_projects == 1
        assert "backend" in loaded.projects
        
        # Verify file exists
        assert (scip_dir / "status.json").exists()

"""
Unit tests for SCIP Audit Repository.

Tests the audit repository functionality for tracking SCIP dependency installations.
Part of AC3: Audit Table for Dependency Installations with Project Context.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from code_indexer.server.repositories.scip_audit import SCIPAuditRepository


class TestSCIPAuditRepository:
    """Unit tests for SCIPAuditRepository class."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def repository(self, temp_db):
        """Create SCIPAuditRepository instance."""
        return SCIPAuditRepository(db_path=temp_db)

    def test_init_creates_table(self, temp_db):
        """Test that initialization creates the audit table."""
        SCIPAuditRepository(db_path=temp_db)

        # Verify table exists
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scip_dependency_installations'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "scip_dependency_installations"

    def test_init_creates_indexes(self, temp_db):
        """Test that initialization creates required indexes."""
        SCIPAuditRepository(db_path=temp_db)

        # Verify indexes exist
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='scip_dependency_installations'"
            )
            indexes = [row[0] for row in cursor.fetchall()]

            # Check for required indexes
            assert "idx_timestamp" in indexes
            assert "idx_repo_alias" in indexes
            assert "idx_job_id" in indexes
            assert "idx_project_language" in indexes

    def test_create_audit_record_success(self, repository):
        """Test successful creation of audit record."""
        record = {
            "job_id": "test-job-123",
            "repo_alias": "test-repo",
            "project_path": "src/myproject",
            "project_language": "python",
            "project_build_system": "pip",
            "package": "numpy",
            "command": "pip install numpy",
            "reasoning": "Required for scientific computing",
            "username": "testuser"
        }

        record_id = repository.create_audit_record(**record)

        # Verify record was created
        assert record_id is not None
        assert isinstance(record_id, int)
        assert record_id > 0

    def test_create_audit_record_atomic_write(self, repository, temp_db):
        """Test that audit record creation is atomic."""
        record = {
            "job_id": "test-job-123",
            "repo_alias": "test-repo",
            "project_path": "src/myproject",
            "project_language": "python",
            "project_build_system": "pip",
            "package": "numpy",
            "command": "pip install numpy",
            "reasoning": None,  # Optional field
            "username": "testuser"
        }

        record_id = repository.create_audit_record(**record)

        # Verify record is immediately queryable
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT * FROM scip_dependency_installations WHERE id = ?",
                (record_id,)
            )
            row = cursor.fetchone()
            assert row is not None

    def test_create_audit_record_with_optional_fields(self, repository):
        """Test creation of audit record with optional fields set to None."""
        record = {
            "job_id": "test-job-123",
            "repo_alias": "test-repo",
            "project_path": None,  # Optional
            "project_language": None,  # Optional
            "project_build_system": None,  # Optional
            "package": "some-package",
            "command": "install command",
            "reasoning": None,  # Optional
            "username": None  # Optional
        }

        record_id = repository.create_audit_record(**record)
        assert record_id is not None

    def test_query_audit_records_no_filters(self, repository):
        """Test querying all audit records without filters."""
        # Create multiple records
        for i in range(3):
            repository.create_audit_record(
                job_id=f"job-{i}",
                repo_alias="test-repo",
                project_path="src/project",
                project_language="python",
                project_build_system="pip",
                package=f"package-{i}",
                command=f"pip install package-{i}",
                reasoning="Test package",
                username="testuser"
            )

        # Query all records
        records, total = repository.query_audit_records()

        assert len(records) == 3
        assert total == 3

    def test_query_audit_records_filter_by_job_id(self, repository):
        """Test filtering audit records by job_id."""
        # Create records with different job IDs
        repository.create_audit_record(
            job_id="job-1",
            repo_alias="repo-1",
            project_path="src/project",
            project_language="python",
            project_build_system="pip",
            package="package-1",
            command="install 1",
            reasoning=None,
            username="user1"
        )
        repository.create_audit_record(
            job_id="job-2",
            repo_alias="repo-2",
            project_path="src/project",
            project_language="javascript",
            project_build_system="npm",
            package="package-2",
            command="install 2",
            reasoning=None,
            username="user2"
        )

        # Query by job_id
        records, total = repository.query_audit_records(job_id="job-1")

        assert len(records) == 1
        assert total == 1
        assert records[0]["job_id"] == "job-1"

    def test_query_audit_records_filter_by_repo_alias(self, repository):
        """Test filtering audit records by repo_alias."""
        # Create records with different repo aliases
        for i in range(2):
            repository.create_audit_record(
                job_id="job-1",
                repo_alias=f"repo-{i}",
                project_path="src/project",
                project_language="python",
                project_build_system="pip",
                package=f"package-{i}",
                command=f"install {i}",
                reasoning=None,
                username="testuser"
            )

        # Query by repo_alias
        records, total = repository.query_audit_records(repo_alias="repo-0")

        assert len(records) == 1
        assert total == 1
        assert records[0]["repo_alias"] == "repo-0"

    def test_query_audit_records_filter_by_project_language(self, repository):
        """Test filtering audit records by project_language."""
        # Create records with different languages
        repository.create_audit_record(
            job_id="job-1",
            repo_alias="repo-1",
            project_path="src/project",
            project_language="python",
            project_build_system="pip",
            package="package-1",
            command="install 1",
            reasoning=None,
            username="user1"
        )
        repository.create_audit_record(
            job_id="job-2",
            repo_alias="repo-2",
            project_path="src/project",
            project_language="javascript",
            project_build_system="npm",
            package="package-2",
            command="install 2",
            reasoning=None,
            username="user2"
        )

        # Query by project_language
        records, total = repository.query_audit_records(project_language="python")

        assert len(records) == 1
        assert total == 1
        assert records[0]["project_language"] == "python"

    def test_query_audit_records_filter_by_build_system(self, repository):
        """Test filtering audit records by project_build_system."""
        # Create records with different build systems
        repository.create_audit_record(
            job_id="job-1",
            repo_alias="repo-1",
            project_path="src/project",
            project_language="python",
            project_build_system="pip",
            package="package-1",
            command="install 1",
            reasoning=None,
            username="user1"
        )
        repository.create_audit_record(
            job_id="job-2",
            repo_alias="repo-2",
            project_path="src/project",
            project_language="python",
            project_build_system="poetry",
            package="package-2",
            command="install 2",
            reasoning=None,
            username="user2"
        )

        # Query by project_build_system
        records, total = repository.query_audit_records(project_build_system="pip")

        assert len(records) == 1
        assert total == 1
        assert records[0]["project_build_system"] == "pip"

    def test_query_audit_records_pagination(self, repository):
        """Test pagination of audit records."""
        # Create 10 records
        for i in range(10):
            repository.create_audit_record(
                job_id=f"job-{i}",
                repo_alias="test-repo",
                project_path="src/project",
                project_language="python",
                project_build_system="pip",
                package=f"package-{i}",
                command=f"install {i}",
                reasoning=None,
                username="testuser"
            )

        # Query with pagination
        records, total = repository.query_audit_records(limit=3, offset=0)
        assert len(records) == 3
        assert total == 10

        # Query next page
        records, total = repository.query_audit_records(limit=3, offset=3)
        assert len(records) == 3
        assert total == 10

    def test_query_audit_records_time_range(self, repository):
        """Test filtering audit records by time range."""
        # Create record
        repository.create_audit_record(
            job_id="job-1",
            repo_alias="test-repo",
            project_path="src/project",
            project_language="python",
            project_build_system="pip",
            package="package-1",
            command="install 1",
            reasoning=None,
            username="testuser"
        )

        # Query with time range (should include the record)
        # Use SQLite-compatible format (YYYY-MM-DD HH:MM:SS)
        now = datetime.now(timezone.utc)
        since = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        until = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        records, total = repository.query_audit_records(
            since=since,
            until=until
        )

        assert len(records) == 1
        assert total == 1

    def test_query_audit_records_multiple_filters(self, repository):
        """Test combining multiple filters."""
        # Create diverse records
        repository.create_audit_record(
            job_id="job-1",
            repo_alias="repo-1",
            project_path="src/project",
            project_language="python",
            project_build_system="pip",
            package="package-1",
            command="install 1",
            reasoning=None,
            username="user1"
        )
        repository.create_audit_record(
            job_id="job-1",
            repo_alias="repo-1",
            project_path="src/project",
            project_language="javascript",
            project_build_system="npm",
            package="package-2",
            command="install 2",
            reasoning=None,
            username="user2"
        )
        repository.create_audit_record(
            job_id="job-2",
            repo_alias="repo-2",
            project_path="src/project",
            project_language="python",
            project_build_system="pip",
            package="package-3",
            command="install 3",
            reasoning=None,
            username="user3"
        )

        # Query with multiple filters
        records, total = repository.query_audit_records(
            job_id="job-1",
            project_language="python"
        )

        assert len(records) == 1
        assert total == 1
        assert records[0]["job_id"] == "job-1"
        assert records[0]["project_language"] == "python"

    def test_query_audit_records_returns_all_fields(self, repository):
        """Test that query returns all expected fields."""
        repository.create_audit_record(
            job_id="job-1",
            repo_alias="test-repo",
            project_path="src/myproject",
            project_language="python",
            project_build_system="pip",
            package="numpy",
            command="pip install numpy",
            reasoning="Scientific computing",
            username="testuser"
        )

        records, total = repository.query_audit_records()

        assert len(records) == 1
        record = records[0]

        # Verify all fields are present
        assert "id" in record
        assert "timestamp" in record
        assert "job_id" in record
        assert "repo_alias" in record
        assert "project_path" in record
        assert "project_language" in record
        assert "project_build_system" in record
        assert "package" in record
        assert "command" in record
        assert "reasoning" in record
        assert "username" in record

        # Verify values
        assert record["job_id"] == "job-1"
        assert record["repo_alias"] == "test-repo"
        assert record["package"] == "numpy"

    def test_error_handling_missing_required_field(self, repository):
        """Test error handling when required field is missing."""
        # job_id is required, should raise error if missing
        with pytest.raises((TypeError, ValueError)):
            repository.create_audit_record(
                # job_id missing
                repo_alias="test-repo",
                project_path="src/project",
                project_language="python",
                project_build_system="pip",
                package="package-1",
                command="install 1",
                reasoning=None,
                username="testuser"
            )

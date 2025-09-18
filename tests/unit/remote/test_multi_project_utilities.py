"""Tests for multi-project manager utility functions.

Tests the utility functions for managing credentials across multiple projects.
"""

import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

from code_indexer.remote.credential_manager import (
    ProjectCredentialManager,
    store_encrypted_credentials,
)
from code_indexer.remote.token_manager import (
    PersistentTokenManager,
    StoredToken,
)
from code_indexer.remote.multi_project_manager import (
    cleanup_project_credentials,
    validate_multi_project_isolation,
    list_project_credentials,
)


class TestMultiProjectManagerUtilities:
    """Test the multi-project manager utility functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = ProjectCredentialManager()

        # Create test projects
        self.projects = {
            "web_app": {
                "path": self.temp_dir / "web_app",
                "username": "webdev",
                "password": "webapp123",
                "server_url": "https://cidx-web.company.com",
            },
            "mobile_app": {
                "path": self.temp_dir / "mobile_app",
                "username": "mobiledev",
                "password": "mobile456",
                "server_url": "https://cidx-mobile.company.com",
            },
        }

        # Create project directories
        for project in self.projects.values():
            project["path"].mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_multi_project_validation_functionality(self):
        """Test the multi-project validation utility function."""
        # Store credentials for projects
        projects_to_validate = {}

        for project_name, config in self.projects.items():
            encrypted_data = self.manager.encrypt_credentials(
                config["username"],
                config["password"],
                config["server_url"],
                str(config["path"]),
            )
            store_encrypted_credentials(config["path"], encrypted_data)

            projects_to_validate[project_name] = {
                "path": config["path"],
                "username": config["username"],
                "server_url": config["server_url"],
                "repo_path": str(config["path"]),
            }

        # Run validation
        validation_results = validate_multi_project_isolation(projects_to_validate)

        # Verify validation results
        assert validation_results["isolation_verified"]
        assert validation_results["cross_access_prevented"]
        assert validation_results["independent_storage"]
        assert len(validation_results["projects_validated"]) == 2
        assert "web_app" in validation_results["projects_validated"]
        assert "mobile_app" in validation_results["projects_validated"]
        assert len(validation_results["issues"]) == 0

    def test_list_project_credentials_functionality(self):
        """Test the project credential listing utility function."""
        # Test project without credentials
        empty_project = self.projects["mobile_app"]
        empty_info = list_project_credentials(empty_project["path"])
        assert empty_info is None

        # Store credentials and test project with credentials
        test_project = self.projects["web_app"]
        encrypted_data = self.manager.encrypt_credentials(
            test_project["username"],
            test_project["password"],
            test_project["server_url"],
            str(test_project["path"]),
        )
        store_encrypted_credentials(test_project["path"], encrypted_data)

        # Store token
        token_manager = PersistentTokenManager(
            project_root=test_project["path"],
            credential_manager=self.manager,
            username=test_project["username"],
            repo_path=str(test_project["path"]),
            server_url=test_project["server_url"],
        )

        test_token = StoredToken(
            token="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0dXNlciIsImlhdCI6MTYzMDAwMDAwMCwiZXhwIjoxNjMwMDg2NDAwfQ.dGVzdF9zaWduYXR1cmU",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"",
        )
        token_manager.store_token(test_token)

        # Test project with credentials and tokens
        creds_info = list_project_credentials(test_project["path"])

        assert creds_info is not None
        assert creds_info["has_credentials"]
        assert creds_info["has_tokens"]
        assert creds_info["credentials_file_size"] > 0
        assert creds_info["token_file_size"] > 0
        assert creds_info["file_permissions_secure"]
        assert creds_info["created_at"] is not None

    def test_project_cleanup_edge_cases(self):
        """Test project cleanup functionality with edge cases."""
        # Test cleanup on non-existent project
        nonexistent_path = self.temp_dir / "nonexistent_project"
        cleanup_results = cleanup_project_credentials(nonexistent_path)

        assert not cleanup_results["credentials_removed"]
        assert not cleanup_results["tokens_removed"]
        assert not cleanup_results["config_dir_removed"]
        assert len(cleanup_results["files_cleaned"]) == 0

        # Test cleanup on project with only config directory (no credential files)
        empty_project = self.projects["mobile_app"]
        config_dir = empty_project["path"] / ".code-indexer"
        config_dir.mkdir(mode=0o700, exist_ok=True)

        cleanup_results = cleanup_project_credentials(empty_project["path"])

        assert not cleanup_results["credentials_removed"]
        assert not cleanup_results["tokens_removed"]
        assert cleanup_results["config_dir_removed"]
        assert len(cleanup_results["files_cleaned"]) == 0

    def test_comprehensive_project_cleanup(self):
        """Test comprehensive project cleanup with all file types."""
        test_project = self.projects["web_app"]

        # Store credentials
        encrypted_data = self.manager.encrypt_credentials(
            test_project["username"],
            test_project["password"],
            test_project["server_url"],
            str(test_project["path"]),
        )
        store_encrypted_credentials(test_project["path"], encrypted_data)

        # Store token
        token_manager = PersistentTokenManager(
            project_root=test_project["path"],
            credential_manager=self.manager,
            username=test_project["username"],
            repo_path=str(test_project["path"]),
            server_url=test_project["server_url"],
        )

        test_token = StoredToken(
            token="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0dXNlciIsImlhdCI6MTYzMDAwMDAwMCwiZXhwIjoxNjMwMDg2NDAwfQ.dGVzdF9zaWduYXR1cmU",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"",
        )
        token_manager.store_token(test_token)

        # Add some additional hidden files
        config_dir = test_project["path"] / ".code-indexer"
        extra_file = config_dir / ".extra_sensitive_data"
        with open(extra_file, "w") as f:
            f.write("sensitive test data")

        # Verify files exist before cleanup
        assert (config_dir / ".creds").exists()
        assert (config_dir / ".token").exists()
        assert extra_file.exists()

        # Perform cleanup
        cleanup_results = cleanup_project_credentials(test_project["path"])

        # Verify comprehensive cleanup
        assert cleanup_results["credentials_removed"]
        assert cleanup_results["tokens_removed"]
        assert cleanup_results["config_dir_removed"]
        assert (
            len(cleanup_results["files_cleaned"]) >= 3
        )  # creds, token, and extra file

        # Verify complete removal
        assert not config_dir.exists()

    def test_multi_project_validation_detects_issues(self):
        """Test that multi-project validation detects security issues."""
        # Create a project with credentials
        test_project = self.projects["web_app"]
        encrypted_data = self.manager.encrypt_credentials(
            test_project["username"],
            test_project["password"],
            test_project["server_url"],
            str(test_project["path"]),
        )
        store_encrypted_credentials(test_project["path"], encrypted_data)

        # Manually make credentials file insecure
        creds_file = test_project["path"] / ".code-indexer" / ".creds"
        creds_file.chmod(0o644)  # Insecure permissions

        projects_to_validate = {
            "web_app": {
                "path": test_project["path"],
                "username": test_project["username"],
                "server_url": test_project["server_url"],
                "repo_path": str(test_project["path"]),
            }
        }

        # Run validation - should detect insecure permissions
        validation_results = validate_multi_project_isolation(projects_to_validate)

        # Should report issues
        assert not validation_results["isolation_verified"]
        assert len(validation_results["issues"]) > 0
        assert any(
            "insecure" in issue.lower() for issue in validation_results["issues"]
        )

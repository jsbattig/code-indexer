"""Tests for multi-project credential isolation and management.

Validates that the credential management system properly isolates
credentials across multiple projects and provides secure cleanup
functionality when projects are removed.
"""

import tempfile
import shutil
import pytest
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from code_indexer.remote.credential_manager import (
    ProjectCredentialManager,
    store_encrypted_credentials,
    load_encrypted_credentials,
    CredentialNotFoundError,
    CredentialDecryptionError,
)
from code_indexer.remote.token_manager import (
    PersistentTokenManager,
    StoredToken,
)
from code_indexer.remote.multi_project_manager import (
    cleanup_project_credentials,
)


class TestMultiProjectCredentialIsolation:
    """Test comprehensive multi-project credential isolation scenarios."""

    def setup_method(self):
        """Set up test fixtures for multi-project testing."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = ProjectCredentialManager()

        # Create multiple test projects
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
            "data_science": {
                "path": self.temp_dir / "analysis" / "data_science",
                "username": "analyst",
                "password": "datascience789",
                "server_url": "https://cidx-ds.company.com",
            },
            "shared_lib": {
                "path": self.temp_dir / "libraries" / "shared_lib",
                "username": "libmaintainer",
                "password": "sharedlib000",
                "server_url": "https://cidx-shared.company.com",
            },
        }

        # Create project directories
        for project in self.projects.values():
            project["path"].mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_multiple_projects_store_different_credentials_simultaneously(self):
        """Test that multiple projects can store different credentials simultaneously."""
        # This test will initially fail because we need to verify the behavior works
        stored_credentials = {}

        # Store credentials for each project
        for project_name, config in self.projects.items():
            encrypted_data = self.manager.encrypt_credentials(
                username=config["username"],
                password=config["password"],
                server_url=config["server_url"],
                repo_path=str(config["path"]),
            )

            store_encrypted_credentials(config["path"], encrypted_data)
            stored_credentials[project_name] = encrypted_data

        # Verify all projects have their own credential files
        for project_name, config in self.projects.items():
            credentials_file = config["path"] / ".code-indexer" / ".creds"
            assert (
                credentials_file.exists()
            ), f"Credentials not found for {project_name}"

            # Verify file permissions are secure (owner read/write only)
            file_mode = credentials_file.stat().st_mode & 0o777
            assert (
                file_mode == 0o600
            ), f"Insecure permissions for {project_name}: {oct(file_mode)}"

        # Verify each project can decrypt its own credentials correctly
        for project_name, config in self.projects.items():
            loaded_encrypted = load_encrypted_credentials(config["path"])

            decrypted_creds = self.manager.decrypt_credentials(
                encrypted_data=loaded_encrypted,
                username=config["username"],
                repo_path=str(config["path"]),
                server_url=config["server_url"],
            )

            assert decrypted_creds.username == config["username"]
            assert decrypted_creds.password == config["password"]
            assert decrypted_creds.server_url == config["server_url"]

        # Verify all encrypted data is different (isolation check)
        credential_values = list(stored_credentials.values())
        for i in range(len(credential_values)):
            for j in range(i + 1, len(credential_values)):
                assert (
                    credential_values[i] != credential_values[j]
                ), "Different projects produced identical encrypted credentials"

    def test_cross_project_credential_access_completely_fails(self):
        """Test that no project can access another project's credentials."""
        # Store credentials in first project
        web_app = self.projects["web_app"]
        encrypted_data = self.manager.encrypt_credentials(
            username=web_app["username"],
            password=web_app["password"],
            server_url=web_app["server_url"],
            repo_path=str(web_app["path"]),
        )
        store_encrypted_credentials(web_app["path"], encrypted_data)

        # Try to decrypt using credentials from all other projects
        other_projects = {k: v for k, v in self.projects.items() if k != "web_app"}

        for project_name, config in other_projects.items():
            with pytest.raises(
                CredentialDecryptionError, match="Failed to decrypt credentials"
            ):
                self.manager.decrypt_credentials(
                    encrypted_data=encrypted_data,
                    username=config["username"],  # Wrong username
                    repo_path=str(config["path"]),  # Wrong project path
                    server_url=config["server_url"],  # Wrong server
                )

    def test_project_credentials_completely_independent_lifecycles(self):
        """Test that project credential lifecycles are completely independent."""
        # Store credentials for two projects
        web_app = self.projects["web_app"]
        mobile_app = self.projects["mobile_app"]

        # Initial storage
        web_encrypted = self.manager.encrypt_credentials(
            web_app["username"],
            web_app["password"],
            web_app["server_url"],
            str(web_app["path"]),
        )
        mobile_encrypted = self.manager.encrypt_credentials(
            mobile_app["username"],
            mobile_app["password"],
            mobile_app["server_url"],
            str(mobile_app["path"]),
        )

        store_encrypted_credentials(web_app["path"], web_encrypted)
        store_encrypted_credentials(mobile_app["path"], mobile_encrypted)

        # Verify both projects can access their credentials
        web_loaded = load_encrypted_credentials(web_app["path"])
        mobile_loaded = load_encrypted_credentials(mobile_app["path"])

        assert web_loaded is not None
        assert mobile_loaded is not None

        # Update credentials for web_app only
        new_web_password = "newwebpass999"
        new_web_encrypted = self.manager.encrypt_credentials(
            web_app["username"],
            new_web_password,
            web_app["server_url"],
            str(web_app["path"]),
        )
        store_encrypted_credentials(web_app["path"], new_web_encrypted)

        # Verify web_app has new credentials
        updated_web_creds = self.manager.decrypt_credentials(
            load_encrypted_credentials(web_app["path"]),
            web_app["username"],
            str(web_app["path"]),
            web_app["server_url"],
        )
        assert updated_web_creds.password == new_web_password

        # Verify mobile_app credentials are unchanged
        mobile_creds = self.manager.decrypt_credentials(
            load_encrypted_credentials(mobile_app["path"]),
            mobile_app["username"],
            str(mobile_app["path"]),
            mobile_app["server_url"],
        )
        assert mobile_creds.password == mobile_app["password"]

        # Remove web_app credentials
        (web_app["path"] / ".code-indexer" / ".creds").unlink()

        # Verify web_app credentials are gone
        with pytest.raises(CredentialNotFoundError):
            load_encrypted_credentials(web_app["path"])

        # Verify mobile_app credentials still work
        mobile_creds_after_removal = self.manager.decrypt_credentials(
            load_encrypted_credentials(mobile_app["path"]),
            mobile_app["username"],
            str(mobile_app["path"]),
            mobile_app["server_url"],
        )
        assert mobile_creds_after_removal.password == mobile_app["password"]

    def test_token_isolation_between_projects(self):
        """Test that JWT tokens are isolated between projects."""
        # This test needs the multi-project token manager functionality
        web_app = self.projects["web_app"]
        mobile_app = self.projects["mobile_app"]

        # Create token managers for each project
        web_token_manager = PersistentTokenManager(
            project_root=web_app["path"],
            credential_manager=self.manager,
            username=web_app["username"],
            repo_path=str(web_app["path"]),
            server_url=web_app["server_url"],
        )

        mobile_token_manager = PersistentTokenManager(
            project_root=mobile_app["path"],
            credential_manager=self.manager,
            username=mobile_app["username"],
            repo_path=str(mobile_app["path"]),
            server_url=mobile_app["server_url"],
        )

        # Create test tokens with properly encoded signatures
        # These are test tokens with valid base64url encoding but fake signatures
        web_token = StoredToken(
            token="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ3ZWJkZXYiLCJpYXQiOjE2MzAwMDAwMDAsImV4cCI6MTYzMDA4NjQwMH0.dGVzdF9zaWduYXR1cmVfd2Vi",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"",
        )

        mobile_token = StoredToken(
            token="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJtb2JpbGVkZXYiLCJpYXQiOjE2MzAwMDAwMDAsImV4cCI6MTYzMDA4NjQwMH0.dGVzdF9zaWduYXR1cmVfbW9iaWxl",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"",
        )

        # Store tokens in each project
        web_token_manager.store_token(web_token)
        mobile_token_manager.store_token(mobile_token)

        # Verify each project can load its own token
        loaded_web_token = web_token_manager.load_token()
        loaded_mobile_token = mobile_token_manager.load_token()

        assert loaded_web_token is not None
        assert loaded_mobile_token is not None

        # Verify tokens are correct by decoding JWT payload (without verification)
        import jwt

        web_payload = jwt.decode(
            loaded_web_token.token, options={"verify_signature": False}
        )
        mobile_payload = jwt.decode(
            loaded_mobile_token.token, options={"verify_signature": False}
        )

        assert web_payload["sub"] == "webdev"
        assert mobile_payload["sub"] == "mobiledev"

        # Verify tokens are stored in separate files
        web_token_file = web_app["path"] / ".code-indexer" / ".token"
        mobile_token_file = mobile_app["path"] / ".code-indexer" / ".token"

        assert web_token_file.exists()
        assert mobile_token_file.exists()
        assert web_token_file != mobile_token_file

        # Verify token files have different content
        with open(web_token_file, "rb") as f:
            web_token_data = f.read()
        with open(mobile_token_file, "rb") as f:
            mobile_token_data = f.read()

        assert web_token_data != mobile_token_data

    def test_same_user_different_servers_complete_isolation(self):
        """Test same username with different servers maintains complete isolation."""
        same_username = "developer"
        same_password = "samepassword"

        # Use same username/password but different servers/projects
        projects_same_user = {
            "prod_server": {
                "path": self.temp_dir / "prod_project",
                "username": same_username,
                "password": same_password,
                "server_url": "https://cidx-prod.company.com",
            },
            "staging_server": {
                "path": self.temp_dir / "staging_project",
                "username": same_username,
                "password": same_password,
                "server_url": "https://cidx-staging.company.com",
            },
            "dev_server": {
                "path": self.temp_dir / "dev_project",
                "username": same_username,
                "password": same_password,
                "server_url": "https://cidx-dev.company.com",
            },
        }

        # Create project directories
        for project in projects_same_user.values():
            project["path"].mkdir(parents=True, exist_ok=True)

        # Store credentials for each server
        encrypted_credentials = {}
        for project_name, config in projects_same_user.items():
            encrypted_data = self.manager.encrypt_credentials(
                config["username"],
                config["password"],
                config["server_url"],
                str(config["path"]),
            )
            store_encrypted_credentials(config["path"], encrypted_data)
            encrypted_credentials[project_name] = encrypted_data

        # Verify all encrypted data is different despite same user/password
        cred_values = list(encrypted_credentials.values())
        for i in range(len(cred_values)):
            for j in range(i + 1, len(cred_values)):
                assert (
                    cred_values[i] != cred_values[j]
                ), "Same user/password produced identical encryption across different servers/projects"

        # Verify cross-server access fails
        for project1_name, config1 in projects_same_user.items():
            encrypted_data1 = encrypted_credentials[project1_name]

            for project2_name, config2 in projects_same_user.items():
                if project1_name != project2_name:
                    # Try to decrypt project1's credentials using project2's context
                    with pytest.raises(CredentialDecryptionError):
                        self.manager.decrypt_credentials(
                            encrypted_data1,
                            config2["username"],  # Same username
                            str(config2["path"]),  # Different path
                            config2["server_url"],  # Different server
                        )

    def test_project_cleanup_removes_all_credential_data(self):
        """Test that project cleanup removes all credential-related data."""
        # This test will initially fail because we need to implement cleanup functionality

        # Set up project with both credentials and tokens
        test_project = self.projects["web_app"]
        project_path = test_project["path"]

        # Store credentials
        encrypted_creds = self.manager.encrypt_credentials(
            test_project["username"],
            test_project["password"],
            test_project["server_url"],
            str(project_path),
        )
        store_encrypted_credentials(project_path, encrypted_creds)

        # Store token
        token_manager = PersistentTokenManager(
            project_root=project_path,
            credential_manager=self.manager,
            username=test_project["username"],
            repo_path=str(project_path),
            server_url=test_project["server_url"],
        )

        test_token = StoredToken(
            token="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0dXNlciIsImlhdCI6MTYzMDAwMDAwMCwiZXhwIjoxNjMwMDg2NDAwfQ.dGVzdF9zaWduYXR1cmU",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"",
        )
        token_manager.store_token(test_token)

        # Verify files exist before cleanup
        creds_file = project_path / ".code-indexer" / ".creds"
        token_file = project_path / ".code-indexer" / ".token"
        config_dir = project_path / ".code-indexer"

        assert creds_file.exists()
        assert token_file.exists()
        assert config_dir.exists()

        # Use the proper cleanup function
        cleanup_results = cleanup_project_credentials(project_path)

        # Verify cleanup results
        assert cleanup_results["credentials_removed"]
        assert cleanup_results["tokens_removed"]
        assert cleanup_results["config_dir_removed"]
        assert (
            len(cleanup_results["files_cleaned"]) >= 2
        )  # At least creds and token files

        # Verify complete cleanup
        assert not creds_file.exists()
        assert not token_file.exists()
        assert not config_dir.exists()  # Should be completely removed

    def test_concurrent_multi_project_credential_operations(self):
        """Test concurrent credential operations across multiple projects."""
        import concurrent.futures

        results = {}
        errors = []

        def store_and_retrieve_credentials(project_name, config):
            """Worker function for concurrent credential operations."""
            try:
                # Store credentials
                encrypted_data = self.manager.encrypt_credentials(
                    config["username"],
                    config["password"],
                    config["server_url"],
                    str(config["path"]),
                )
                store_encrypted_credentials(config["path"], encrypted_data)

                # Small delay to increase chance of race conditions
                time.sleep(0.01)

                # Retrieve and decrypt
                loaded_data = load_encrypted_credentials(config["path"])
                decrypted_creds = self.manager.decrypt_credentials(
                    loaded_data,
                    config["username"],
                    str(config["path"]),
                    config["server_url"],
                )

                results[project_name] = {
                    "success": True,
                    "username": decrypted_creds.username,
                    "password": decrypted_creds.password,
                    "server_url": decrypted_creds.server_url,
                }

            except Exception as e:
                errors.append(f"{project_name}: {str(e)}")
                results[project_name] = {"success": False, "error": str(e)}

        # Run concurrent operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(store_and_retrieve_credentials, name, config): name
                for name, config in self.projects.items()
            }

            concurrent.futures.wait(futures)

        # Verify all operations succeeded
        assert len(errors) == 0, f"Concurrent operations failed: {errors}"

        for project_name, result in results.items():
            assert result[
                "success"
            ], f"Project {project_name} failed: {result.get('error')}"

            config = self.projects[project_name]
            assert result["username"] == config["username"]
            assert result["password"] == config["password"]
            assert result["server_url"] == config["server_url"]

    def test_multi_project_credential_security_boundary_enforcement(self):
        """Test that security boundaries are strictly enforced across projects."""
        # Create projects with overlapping security contexts but should remain isolated
        base_path = self.temp_dir / "security_test"

        security_projects = {
            "client_a": {
                "path": base_path / "client_a",
                "username": "admin",  # Same username
                "password": "secret123",  # Same password
                "server_url": "https://shared.server.com",  # Same server
            },
            "client_b": {
                "path": base_path / "client_b",
                "username": "admin",  # Same username
                "password": "secret123",  # Same password
                "server_url": "https://shared.server.com",  # Same server
            },
            "client_c": {
                "path": base_path / "department" / "client_c",
                "username": "admin",  # Same username
                "password": "secret123",  # Same password
                "server_url": "https://shared.server.com",  # Same server
            },
        }

        # Create directories
        for project in security_projects.values():
            project["path"].mkdir(parents=True, exist_ok=True)

        # Store identical credentials in different project paths
        encrypted_data = {}
        for project_name, config in security_projects.items():
            encrypted_data[project_name] = self.manager.encrypt_credentials(
                config["username"],
                config["password"],
                config["server_url"],
                str(config["path"]),
            )
            store_encrypted_credentials(config["path"], encrypted_data[project_name])

        # Verify that despite identical user/pass/server, encryption is different
        # because of different project paths
        cred_values = list(encrypted_data.values())
        for i in range(len(cred_values)):
            for j in range(i + 1, len(cred_values)):
                assert (
                    cred_values[i] != cred_values[j]
                ), "Identical credentials in different projects produced same encryption"

        # Verify strict cross-project access denial
        for project1_name, project1_encrypted in encrypted_data.items():
            for project2_name, project2_config in security_projects.items():
                if project1_name != project2_name:
                    # Should fail even with identical username/password/server
                    # because project path differs
                    with pytest.raises(CredentialDecryptionError):
                        self.manager.decrypt_credentials(
                            project1_encrypted,
                            project2_config["username"],
                            str(project2_config["path"]),
                            project2_config["server_url"],
                        )

    def test_project_credential_compromise_containment(self):
        """Test that credential compromise in one project doesn't affect others."""
        # Simulate a scenario where one project's credentials are compromised
        compromised_project = self.projects["web_app"]
        safe_projects = {k: v for k, v in self.projects.items() if k != "web_app"}

        # Store credentials in all projects
        for project_name, config in self.projects.items():
            encrypted_data = self.manager.encrypt_credentials(
                config["username"],
                config["password"],
                config["server_url"],
                str(config["path"]),
            )
            store_encrypted_credentials(config["path"], encrypted_data)

        # Simulate compromise: attacker gets the encrypted credential file
        compromised_creds_file = (
            compromised_project["path"] / ".code-indexer" / ".creds"
        )
        with open(compromised_creds_file, "rb") as f:
            compromised_encrypted_data = f.read()

        # Verify attacker cannot use compromised credentials in other projects
        for project_name, safe_config in safe_projects.items():
            # Even if attacker knows the original username/server,
            # they cannot decrypt in a different project path
            with pytest.raises(CredentialDecryptionError):
                self.manager.decrypt_credentials(
                    compromised_encrypted_data,
                    compromised_project["username"],  # Known from compromise
                    str(safe_config["path"]),  # Different project path
                    compromised_project["server_url"],  # Known from compromise
                )

            # Attacker also cannot use legitimate project context
            # with compromised data
            with pytest.raises(CredentialDecryptionError):
                self.manager.decrypt_credentials(
                    compromised_encrypted_data,
                    safe_config["username"],  # Different username
                    str(safe_config["path"]),  # Different project
                    safe_config["server_url"],  # Different server
                )

        # Verify safe projects remain completely functional
        for project_name, config in safe_projects.items():
            loaded_creds = load_encrypted_credentials(config["path"])
            decrypted_creds = self.manager.decrypt_credentials(
                loaded_creds,
                config["username"],
                str(config["path"]),
                config["server_url"],
            )

            assert decrypted_creds.username == config["username"]
            assert decrypted_creds.password == config["password"]
            assert decrypted_creds.server_url == config["server_url"]

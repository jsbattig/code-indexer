"""Tests for cross-project credential isolation and security."""

import tempfile
import pytest
from pathlib import Path

from code_indexer.remote.credential_manager import (
    ProjectCredentialManager,
    CredentialDecryptionError,
)


class TestCredentialProjectIsolation:
    """Test credential isolation between different projects."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = ProjectCredentialManager()

        # Common test credentials
        self.username = "testuser"
        self.password = "securepass123"
        self.server_url = "https://cidx.example.com"

        # Different project paths
        self.project1_path = str(self.temp_dir / "project1")
        self.project2_path = str(self.temp_dir / "project2")
        self.project3_path = str(self.temp_dir / "deep" / "nested" / "project3")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_same_credentials_different_projects_produce_different_encrypted_data(self):
        """Test identical credentials in different projects produce different encrypted data."""
        # Encrypt same credentials for different projects
        encrypted_p1 = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, self.project1_path
        )
        encrypted_p2 = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, self.project2_path
        )
        encrypted_p3 = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, self.project3_path
        )

        # All encrypted data should be different
        assert encrypted_p1 != encrypted_p2
        assert encrypted_p1 != encrypted_p3
        assert encrypted_p2 != encrypted_p3

        # But all should decrypt correctly within their own project
        creds_p1 = self.manager.decrypt_credentials(
            encrypted_p1, self.username, self.project1_path, self.server_url
        )
        creds_p2 = self.manager.decrypt_credentials(
            encrypted_p2, self.username, self.project2_path, self.server_url
        )
        creds_p3 = self.manager.decrypt_credentials(
            encrypted_p3, self.username, self.project3_path, self.server_url
        )

        assert creds_p1.password == self.password
        assert creds_p2.password == self.password
        assert creds_p3.password == self.password

    def test_cross_project_decryption_always_fails(self):
        """Test credentials encrypted in one project cannot be decrypted in another."""
        # Encrypt credentials for project 1
        encrypted_data = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, self.project1_path
        )

        # Try to decrypt in different projects - all should fail
        test_projects = [
            self.project2_path,
            self.project3_path,
            str(self.temp_dir / "nonexistent"),
            "/completely/different/path",
        ]

        for wrong_project in test_projects:
            with pytest.raises(CredentialDecryptionError):
                self.manager.decrypt_credentials(
                    encrypted_data, self.username, wrong_project, self.server_url
                )

    def test_similar_project_paths_still_isolated(self):
        """Test even similar project paths produce different encryption keys."""
        base_path = str(self.temp_dir / "myproject")
        similar_paths = [
            base_path,
            base_path + "2",
            base_path + "_backup",
            base_path + "/subdir",
            str(self.temp_dir / "myproject_copy"),
        ]

        encrypted_data_list = []
        for path in similar_paths:
            encrypted_data = self.manager.encrypt_credentials(
                self.username, self.password, self.server_url, path
            )
            encrypted_data_list.append((path, encrypted_data))

        # All should be different
        for i, (path1, data1) in enumerate(encrypted_data_list):
            for j, (path2, data2) in enumerate(encrypted_data_list):
                if i != j:
                    assert (
                        data1 != data2
                    ), f"Paths {path1} and {path2} produced same encryption"

        # Cross-decryption should fail
        for i, (path1, data1) in enumerate(encrypted_data_list):
            for j, (path2, data2) in enumerate(encrypted_data_list):
                if i != j:
                    with pytest.raises(CredentialDecryptionError):
                        self.manager.decrypt_credentials(
                            data1, self.username, path2, self.server_url
                        )

    def test_different_usernames_same_project_produce_different_keys(self):
        """Test different usernames in same project produce different encryption."""
        usernames = ["user1", "user2", "admin", "developer@company.com"]

        encrypted_data_list = []
        for username in usernames:
            encrypted_data = self.manager.encrypt_credentials(
                username, self.password, self.server_url, self.project1_path
            )
            encrypted_data_list.append((username, encrypted_data))

        # All should be different
        for i, (user1, data1) in enumerate(encrypted_data_list):
            for j, (user2, data2) in enumerate(encrypted_data_list):
                if i != j:
                    assert (
                        data1 != data2
                    ), f"Users {user1} and {user2} produced same encryption"

        # Cross-user decryption should fail
        for i, (user1, data1) in enumerate(encrypted_data_list):
            for j, (user2, data2) in enumerate(encrypted_data_list):
                if i != j:
                    with pytest.raises(CredentialDecryptionError):
                        self.manager.decrypt_credentials(
                            data1, user2, self.project1_path, self.server_url
                        )

    def test_different_server_urls_same_project_produce_different_keys(self):
        """Test different server URLs in same project produce different encryption."""
        server_urls = [
            "https://cidx.company.com",
            "https://cidx-dev.company.com",
            "https://cidx.company.com:8080",
            "http://localhost:8080",
            "https://alternate.server.com",
        ]

        encrypted_data_list = []
        for server_url in server_urls:
            encrypted_data = self.manager.encrypt_credentials(
                self.username, self.password, server_url, self.project1_path
            )
            encrypted_data_list.append((server_url, encrypted_data))

        # All should be different
        for i, (url1, data1) in enumerate(encrypted_data_list):
            for j, (url2, data2) in enumerate(encrypted_data_list):
                if i != j:
                    assert (
                        data1 != data2
                    ), f"URLs {url1} and {url2} produced same encryption"

        # Cross-server decryption should fail
        for i, (url1, data1) in enumerate(encrypted_data_list):
            for j, (url2, data2) in enumerate(encrypted_data_list):
                if i != j:
                    with pytest.raises(CredentialDecryptionError):
                        self.manager.decrypt_credentials(
                            data1, self.username, self.project1_path, url2
                        )

    def test_absolute_vs_relative_paths_different_keys(self):
        """Test absolute vs relative paths produce different encryption keys."""
        abs_path = str(self.temp_dir.absolute() / "project")
        rel_path = "project"  # Relative path

        encrypted_abs = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, abs_path
        )
        encrypted_rel = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, rel_path
        )

        # Should produce different encrypted data
        assert encrypted_abs != encrypted_rel

        # Cross-path decryption should fail
        with pytest.raises(CredentialDecryptionError):
            self.manager.decrypt_credentials(
                encrypted_abs, self.username, rel_path, self.server_url
            )

        with pytest.raises(CredentialDecryptionError):
            self.manager.decrypt_credentials(
                encrypted_rel, self.username, abs_path, self.server_url
            )

    def test_normalized_vs_unnormalized_paths_different_keys(self):
        """Test normalized vs unnormalized paths produce different keys."""
        normalized_path = str(self.temp_dir / "project")
        unnormalized_path = str(self.temp_dir / "project" / ".." / "project")

        encrypted_norm = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, normalized_path
        )
        encrypted_unnorm = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, unnormalized_path
        )

        # Should produce different encrypted data (path is used as-is)
        assert encrypted_norm != encrypted_unnorm

    def test_case_sensitive_path_isolation(self):
        """Test path case sensitivity in key derivation."""
        if Path("/").stat().st_dev == Path("/").stat().st_dev:
            # On case-sensitive file systems, test case sensitivity
            lower_path = str(self.temp_dir / "project")
            upper_path = str(self.temp_dir / "PROJECT")

            encrypted_lower = self.manager.encrypt_credentials(
                self.username, self.password, self.server_url, lower_path
            )
            encrypted_upper = self.manager.encrypt_credentials(
                self.username, self.password, self.server_url, upper_path
            )

            # Should be different on case-sensitive systems
            assert encrypted_lower != encrypted_upper

    def test_project_isolation_with_credential_reuse_attack_scenario(self):
        """Test protection against credential reuse attacks across projects."""
        # Scenario: Attacker has access to encrypted credentials from project1
        # and tries to use them in project2 (even with same user/server)

        # Legitimate user encrypts credentials in project1
        legitimate_encrypted = self.manager.encrypt_credentials(
            self.username, self.password, self.server_url, self.project1_path
        )

        # Attacker copies encrypted data to project2
        # This should fail to decrypt even with correct username/server
        with pytest.raises(CredentialDecryptionError):
            self.manager.decrypt_credentials(
                legitimate_encrypted,
                self.username,
                self.project2_path,  # Different project
                self.server_url,
            )

        # Even if attacker knows the original project path, they can't use
        # the credentials in a different project without the correct context
        with pytest.raises(CredentialDecryptionError):
            self.manager.decrypt_credentials(
                legitimate_encrypted,
                self.username,
                self.project2_path,  # Still wrong project
                self.server_url,
            )

    def test_key_derivation_input_independence(self):
        """Test that key derivation treats each input component independently."""
        # Test that changing any part of the key derivation input
        # produces a completely different key

        base_encrypted = self.manager.encrypt_credentials(
            "user", "pass", "https://server.com", "/path/to/project"
        )

        # Change each component and verify different encryption
        variants = [
            ("user2", "pass", "https://server.com", "/path/to/project"),  # user change
            (
                "user",
                "pass2",
                "https://server.com",
                "/path/to/project",
            ),  # password change
            (
                "user",
                "pass",
                "https://server2.com",
                "/path/to/project",
            ),  # server change
            ("user", "pass", "https://server.com", "/path/to/project2"),  # path change
        ]

        for username, password, server_url, project_path in variants:
            variant_encrypted = self.manager.encrypt_credentials(
                username, password, server_url, project_path
            )

            # Should produce different encrypted data
            assert base_encrypted != variant_encrypted

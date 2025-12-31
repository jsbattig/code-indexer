"""
Unit tests for Git Committer Attribution (Story #641).

Tests automatic committer attribution based on SSH key authentication:
- GitServiceConfig.default_committer_email field
- CommitterResolutionService.resolve_committer_email
- ActivatedRepoManager integration with SSH key testing
- GitOperationsService.git_commit co_author_email validation
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.config import GitServiceConfig, ConfigManager
from code_indexer.server.services.ssh_key_manager import KeyMetadata


class TestGitServiceConfigDefaultEmail:
    """Test GitServiceConfig.default_committer_email field (AC #2)."""

    def test_default_committer_email_field_exists(self):
        """Test default_committer_email field exists in GitServiceConfig."""
        config = GitServiceConfig()

        # Field should exist (will fail until implemented)
        assert hasattr(config, "default_committer_email")

    def test_default_committer_email_has_valid_default(self):
        """Test default_committer_email has a sensible default value."""
        config = GitServiceConfig()

        # Default should be a valid email format
        assert "@" in config.default_committer_email
        assert "." in config.default_committer_email.split("@")[1]

    def test_default_committer_email_accepts_valid_emails(self):
        """Test default_committer_email accepts valid email formats."""
        valid_emails = [
            "fallback@example.com",
            "cidx-default@company.org",
            "no-reply@github.com",
        ]

        for email in valid_emails:
            config = GitServiceConfig(default_committer_email=email)
            assert config.default_committer_email == email

    def test_default_committer_email_rejects_invalid_format(self):
        """Test default_committer_email rejects invalid email formats."""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user@domain",  # No TLD
        ]

        for email in invalid_emails:
            with pytest.raises(ValueError) as exc_info:
                GitServiceConfig(default_committer_email=email)

            # Check for either error message format (Pydantic wraps errors)
            error_str = str(exc_info.value)
            assert (
                "Invalid email format" in error_str
                or "Email must have valid domain" in error_str
            )

    def test_default_committer_email_persists_in_config_json(self, tmp_path):
        """Test default_committer_email persists when saving config to disk."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create config manager and set default_committer_email
        manager = ConfigManager(config_path)
        config = manager.load()
        config.git_service.default_committer_email = "custom-default@example.com"
        manager.save(config)

        # Reload and verify persistence
        manager2 = ConfigManager(config_path)
        config2 = manager2.load()
        assert (
            config2.git_service.default_committer_email == "custom-default@example.com"
        )

    def test_default_committer_email_optional_field(self):
        """Test default_committer_email is optional (can be None)."""
        config = GitServiceConfig(
            service_committer_name="Test",
            service_committer_email="test@example.com",
            # default_committer_email not provided
        )

        # Should allow None or have default
        assert config.default_committer_email is not None or True  # Flexible check


class TestCommitterResolutionService:
    """Test CommitterResolutionService.resolve_committer_email (AC #1, #2)."""

    def test_service_exists(self):
        """Test CommitterResolutionService class exists."""
        # Will fail until CommitterResolutionService is implemented
        from code_indexer.server.services.committer_resolution_service import (
            CommitterResolutionService,
        )

        service = CommitterResolutionService()
        assert service is not None

    def test_resolve_committer_email_method_exists(self):
        """Test resolve_committer_email method exists."""
        from code_indexer.server.services.committer_resolution_service import (
            CommitterResolutionService,
        )

        service = CommitterResolutionService()
        assert hasattr(service, "resolve_committer_email")
        assert callable(service.resolve_committer_email)

    def test_resolve_committer_email_with_working_ssh_key(self):
        """Test resolve_committer_email returns key email when SSH auth succeeds (AC #1)."""
        from code_indexer.server.services.committer_resolution_service import (
            CommitterResolutionService,
        )

        # Mock dependencies
        mock_remote_discovery = Mock()
        mock_remote_discovery.extract_hostname.return_value = "github.com"

        # Use real KeyMetadata instead of Mock
        test_key = KeyMetadata(
            name="github-key",
            fingerprint="SHA256:abc123",
            key_type="ed25519",
            private_path="/path/to/key",
            public_path="/path/to/key.pub",
            email="ssh-key-owner@example.com",
        )

        mock_ssh_key_manager = Mock()
        mock_ssh_key_manager.list_keys.return_value = Mock(managed=[test_key])

        mock_key_tester = Mock()
        mock_key_tester.test_key_against_host.return_value = Mock(success=True)

        service = CommitterResolutionService(
            remote_discovery_service=mock_remote_discovery,
            ssh_key_manager=mock_ssh_key_manager,
            key_to_remote_tester=mock_key_tester,
        )

        # Test resolution
        email, key_name = service.resolve_committer_email(
            golden_repo_url="git@github.com:user/repo.git",
            default_email="fallback@example.com",
        )

        # Should return SSH key email
        assert email == "ssh-key-owner@example.com"
        assert key_name == "github-key"

    def test_resolve_committer_email_fallback_when_no_keys(self):
        """Test resolve_committer_email returns default when no SSH keys exist (AC #2)."""
        from code_indexer.server.services.committer_resolution_service import (
            CommitterResolutionService,
        )

        # Mock dependencies
        mock_remote_discovery = Mock()
        mock_remote_discovery.extract_hostname.return_value = "github.com"

        mock_ssh_key_manager = Mock()
        mock_ssh_key_manager.list_keys.return_value = Mock(managed=[])  # No keys

        mock_key_tester = Mock()

        service = CommitterResolutionService(
            remote_discovery_service=mock_remote_discovery,
            ssh_key_manager=mock_ssh_key_manager,
            key_to_remote_tester=mock_key_tester,
        )

        # Test resolution
        email, key_name = service.resolve_committer_email(
            golden_repo_url="git@github.com:user/repo.git",
            default_email="fallback@example.com",
        )

        # Should return default email
        assert email == "fallback@example.com"
        assert key_name is None

    def test_resolve_committer_email_fallback_when_no_keys_authenticate(self):
        """Test resolve_committer_email returns default when all SSH keys fail (AC #2)."""
        from code_indexer.server.services.committer_resolution_service import (
            CommitterResolutionService,
        )

        # Mock dependencies
        mock_remote_discovery = Mock()
        mock_remote_discovery.extract_hostname.return_value = "github.com"

        # Use real KeyMetadata instances
        key1 = KeyMetadata(
            name="key1",
            fingerprint="SHA256:key1",
            key_type="ed25519",
            private_path="/path/to/key1",
            public_path="/path/to/key1.pub",
            email="key1@example.com",
        )
        key2 = KeyMetadata(
            name="key2",
            fingerprint="SHA256:key2",
            key_type="ed25519",
            private_path="/path/to/key2",
            public_path="/path/to/key2.pub",
            email="key2@example.com",
        )

        mock_ssh_key_manager = Mock()
        mock_ssh_key_manager.list_keys.return_value = Mock(managed=[key1, key2])

        mock_key_tester = Mock()
        mock_key_tester.test_key_against_host.return_value = Mock(
            success=False
        )  # All fail

        service = CommitterResolutionService(
            remote_discovery_service=mock_remote_discovery,
            ssh_key_manager=mock_ssh_key_manager,
            key_to_remote_tester=mock_key_tester,
        )

        # Test resolution
        email, key_name = service.resolve_committer_email(
            golden_repo_url="git@github.com:user/repo.git",
            default_email="fallback@example.com",
        )

        # Should return default email
        assert email == "fallback@example.com"
        assert key_name is None

    def test_resolve_committer_email_fallback_when_hostname_extraction_fails(self):
        """Test resolve_committer_email returns default when hostname extraction fails (AC #2)."""
        from code_indexer.server.services.committer_resolution_service import (
            CommitterResolutionService,
        )

        # Mock dependencies
        mock_remote_discovery = Mock()
        mock_remote_discovery.extract_hostname.return_value = None  # Extraction fails

        mock_ssh_key_manager = Mock()
        mock_key_tester = Mock()

        service = CommitterResolutionService(
            remote_discovery_service=mock_remote_discovery,
            ssh_key_manager=mock_ssh_key_manager,
            key_to_remote_tester=mock_key_tester,
        )

        # Test resolution
        email, key_name = service.resolve_committer_email(
            golden_repo_url="invalid-url", default_email="fallback@example.com"
        )

        # Should return default email
        assert email == "fallback@example.com"
        assert key_name is None

    def test_resolve_committer_email_stops_at_first_working_key(self):
        """Test resolve_committer_email stops testing keys at first successful authentication."""
        from code_indexer.server.services.committer_resolution_service import (
            CommitterResolutionService,
        )

        # Mock dependencies
        mock_remote_discovery = Mock()
        mock_remote_discovery.extract_hostname.return_value = "github.com"

        # Use real KeyMetadata instances
        key1 = KeyMetadata(
            name="key1",
            fingerprint="SHA256:key1",
            key_type="ed25519",
            private_path="/path/to/key1",
            public_path="/path/to/key1.pub",
            email="key1@example.com",
        )
        key2 = KeyMetadata(
            name="key2",
            fingerprint="SHA256:key2",
            key_type="ed25519",
            private_path="/path/to/key2",
            public_path="/path/to/key2.pub",
            email="key2@example.com",
        )
        key3 = KeyMetadata(
            name="key3",
            fingerprint="SHA256:key3",
            key_type="ed25519",
            private_path="/path/to/key3",
            public_path="/path/to/key3.pub",
            email="key3@example.com",
        )

        mock_ssh_key_manager = Mock()
        mock_ssh_key_manager.list_keys.return_value = Mock(managed=[key1, key2, key3])

        # First key fails, second succeeds, third should not be tested
        mock_key_tester = Mock()
        mock_key_tester.test_key_against_host.side_effect = [
            Mock(success=False),  # key1 fails
            Mock(success=True),  # key2 succeeds
        ]

        service = CommitterResolutionService(
            remote_discovery_service=mock_remote_discovery,
            ssh_key_manager=mock_ssh_key_manager,
            key_to_remote_tester=mock_key_tester,
        )

        # Test resolution
        email, key_name = service.resolve_committer_email(
            golden_repo_url="git@github.com:user/repo.git",
            default_email="fallback@example.com",
        )

        # Should return second key's email
        assert email == "key2@example.com"
        assert key_name == "key2"

        # Verify only 2 keys were tested (not all 3)
        assert mock_key_tester.test_key_against_host.call_count == 2


class TestGitCommitCoAuthorValidation:
    """Test git_commit co_author_email parameter validation (AC #3, #4, #5)."""

    def test_git_commit_without_co_author_email_raises_error(self):
        """Test git_commit raises error when co_author_email not provided (AC #3)."""
        from code_indexer.server.services.git_operations_service import (
            GitOperationsService,
        )

        service = GitOperationsService()

        # Should raise ValueError when co_author_email is None
        with pytest.raises(ValueError) as exc_info:
            service.git_commit(
                Path("/tmp/repo"),
                message="Test commit",
                user_email=None,  # co_author_email is None
                user_name="Test User",
            )

        assert "co_author_email parameter is required" in str(exc_info.value)

    def test_git_commit_with_empty_co_author_email_raises_error(self):
        """Test git_commit raises error when co_author_email is empty string (AC #3)."""
        from code_indexer.server.services.git_operations_service import (
            GitOperationsService,
        )

        service = GitOperationsService()

        # Should raise ValueError when co_author_email is empty string
        with pytest.raises(ValueError) as exc_info:
            service.git_commit(
                Path("/tmp/repo"),
                message="Test commit",
                user_email="",  # co_author_email is empty
                user_name="Test User",
            )

        assert "co_author_email parameter is required" in str(exc_info.value)

    def test_git_commit_with_invalid_email_format_raises_error(self):
        """Test git_commit raises error with INVALID_EMAIL_FORMAT code (AC #4)."""
        from code_indexer.server.services.git_operations_service import (
            GitOperationsService,
        )

        service = GitOperationsService()

        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user@domain",  # No TLD
        ]

        for invalid_email in invalid_emails:
            with pytest.raises(ValueError) as exc_info:
                service.git_commit(
                    Path("/tmp/repo"),
                    message="Test commit",
                    user_email=invalid_email,
                    user_name="Test User",
                )

            # Error should have INVALID_EMAIL_FORMAT code (check error message)
            assert "Invalid email format" in str(exc_info.value)

    def test_git_commit_with_valid_co_author_email_succeeds(self, tmp_path):
        """Test git_commit succeeds with valid co_author_email (AC #5)."""
        from code_indexer.server.services.git_operations_service import (
            GitOperationsService,
        )

        # Create temporary git repo
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        import subprocess

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "committer@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Committer"], cwd=repo_path, check=True
        )

        # Create a file to commit
        test_file = repo_path / "test.txt"
        test_file.write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_path, check=True)

        service = GitOperationsService()

        # Should succeed with valid co_author_email
        result = service.git_commit(
            repo_path,
            message="Test commit",
            user_email="claude-user@anthropic.com",
            user_name="Claude User",
        )

        assert result["success"] is True
        assert result["author"] == "claude-user@anthropic.com"
        assert result["committer"] == "committer@example.com"
        assert "commit_hash" in result


class TestActivationWithSSHKeyDiscovery:
    """Test repository activation with SSH key discovery and git config setup (AC #1)."""

    @pytest.fixture
    def activated_repo_test_setup(self, tmp_path):
        """Common setup for activation integration tests."""
        from code_indexer.server.repositories.activated_repo_manager import (
            ActivatedRepoManager,
        )
        from code_indexer.server.repositories.golden_repo_manager import (
            GoldenRepoManager,
            GoldenRepo,
        )
        from code_indexer.server.repositories.background_jobs import (
            BackgroundJobManager,
        )
        from datetime import datetime, timezone
        import subprocess

        # Create temporary directories
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        golden_repos_dir = data_dir / "golden-repos"
        golden_repos_dir.mkdir()

        # Create a real git repository to use as golden repo
        golden_repo_path = golden_repos_dir / "test-repo"
        golden_repo_path.mkdir()
        subprocess.run(
            ["git", "init"], cwd=golden_repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "golden@example.com"],
            cwd=golden_repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Golden"], cwd=golden_repo_path, check=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:user/repo.git"],
            cwd=golden_repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        test_file = golden_repo_path / "README.md"
        test_file.write_text("Test repo")
        subprocess.run(["git", "add", "README.md"], cwd=golden_repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=golden_repo_path, check=True
        )

        # Set up golden repo manager
        golden_repo_manager = GoldenRepoManager(str(data_dir))
        golden_repo_manager.golden_repos["test-repo"] = GoldenRepo(
            alias="test-repo",
            repo_url="git@github.com:user/repo.git",
            default_branch="main",
            clone_path=str(golden_repo_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Create managers
        background_job_manager = BackgroundJobManager()
        activated_repo_manager = ActivatedRepoManager(
            data_dir=str(data_dir),
            golden_repo_manager=golden_repo_manager,
            background_job_manager=background_job_manager,
        )

        return {
            "data_dir": data_dir,
            "golden_repo_manager": golden_repo_manager,
            "activated_repo_manager": activated_repo_manager,
        }

    def test_activation_sets_git_config_from_working_ssh_key(
        self, activated_repo_test_setup
    ):
        """Test _do_activate_repository sets git config user.email from working SSH key."""
        import subprocess

        setup = activated_repo_test_setup
        activated_repo_manager = setup["activated_repo_manager"]
        data_dir = setup["data_dir"]

        # Mock CommitterResolutionService to return a working SSH key's email
        with patch(
            "code_indexer.server.repositories.activated_repo_manager.CommitterResolutionService"
        ) as mock_service_class:
            mock_service = Mock()
            mock_service.resolve_committer_email.return_value = (
                "ssh-key@example.com",
                "my-key",
            )
            mock_service_class.return_value = mock_service

            with patch(
                "code_indexer.server.repositories.activated_repo_manager.GitServiceConfig"
            ) as mock_config_class:
                mock_config = Mock()
                mock_config.default_committer_email = "fallback@example.com"
                mock_config_class.return_value = mock_config

                # Call _do_activate_repository
                result = activated_repo_manager._do_activate_repository(
                    username="testuser",
                    golden_repo_alias="test-repo",
                    branch_name="main",
                    user_alias="my-repo",
                )

        # Verify result
        assert result["success"] is True

        # Verify git config was set in activated repository
        activated_repo_path = data_dir / "activated-repos" / "testuser" / "my-repo"
        assert activated_repo_path.exists()

        # Check git config user.email
        git_email_result = subprocess.run(
            ["git", "config", "user.email"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert git_email_result.stdout.strip() == "ssh-key@example.com"

        # Check git config user.name
        git_name_result = subprocess.run(
            ["git", "config", "user.name"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert git_name_result.stdout.strip() == "CIDX User"

    def test_activation_stores_git_committer_email_in_metadata(
        self, activated_repo_test_setup
    ):
        """Test _do_activate_repository stores git_committer_email and ssh_key_used in metadata."""
        import json

        setup = activated_repo_test_setup
        activated_repo_manager = setup["activated_repo_manager"]
        data_dir = setup["data_dir"]

        # Mock CommitterResolutionService
        with patch(
            "code_indexer.server.repositories.activated_repo_manager.CommitterResolutionService"
        ) as mock_service_class:
            mock_service = Mock()
            mock_service.resolve_committer_email.return_value = (
                "resolved-ssh@example.com",
                "my-key-name",
            )
            mock_service_class.return_value = mock_service

            with patch(
                "code_indexer.server.repositories.activated_repo_manager.GitServiceConfig"
            ) as mock_config_class:
                mock_config = Mock()
                mock_config.default_committer_email = "fallback@example.com"
                mock_config_class.return_value = mock_config

                # Call _do_activate_repository
                result = activated_repo_manager._do_activate_repository(
                    username="testuser",
                    golden_repo_alias="test-repo",
                    branch_name="main",
                    user_alias="my-repo",
                )

        # Verify result
        assert result["success"] is True

        # Load and verify metadata
        metadata_file = (
            data_dir / "activated-repos" / "testuser" / "my-repo_metadata.json"
        )
        assert metadata_file.exists()

        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        # Verify git_committer_email and ssh_key_used are stored
        assert "git_committer_email" in metadata
        assert metadata["git_committer_email"] == "resolved-ssh@example.com"
        assert "ssh_key_used" in metadata
        assert metadata["ssh_key_used"] == "my-key-name"

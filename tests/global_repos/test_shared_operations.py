"""
Tests for GlobalRepoOperations shared business logic.

TDD tests written FIRST before implementation.
"""

import json
import os
import tempfile
from pathlib import Path
import pytest
from code_indexer.global_repos.shared_operations import GlobalRepoOperations


@pytest.fixture
def temp_golden_repos_dir():
    """Create temporary golden repos directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        golden_dir = Path(tmpdir) / "golden-repos"
        golden_dir.mkdir(parents=True)

        # Create aliases subdirectory
        (golden_dir / "aliases").mkdir()

        # Create empty registry file
        registry_file = golden_dir / "global_registry.json"
        registry_file.write_text(json.dumps({}))

        yield str(golden_dir)


@pytest.fixture
def golden_repos_dir_with_data(temp_golden_repos_dir):
    """Create golden repos directory with test data."""
    # Create test registry data
    test_repos = {
        "repo1-global": {
            "repo_name": "repo1",
            "alias_name": "repo1-global",
            "repo_url": "https://github.com/test/repo1.git",
            "index_path": "/path/to/repo1",
            "created_at": "2025-01-01T00:00:00+00:00",
            "last_refresh": "2025-01-01T12:00:00+00:00"
        },
        "repo2-global": {
            "repo_name": "repo2",
            "alias_name": "repo2-global",
            "repo_url": "https://github.com/test/repo2.git",
            "index_path": "/path/to/repo2",
            "created_at": "2025-01-02T00:00:00+00:00",
            "last_refresh": "2025-01-02T12:00:00+00:00"
        }
    }

    registry_file = Path(temp_golden_repos_dir) / "global_registry.json"
    registry_file.write_text(json.dumps(test_repos, indent=2))

    return temp_golden_repos_dir


class TestListRepos:
    """Tests for list_repos functionality."""

    def test_list_repos_returns_all_global_repos(self, golden_repos_dir_with_data):
        """Test that list_repos returns all registered global repos."""
        ops = GlobalRepoOperations(golden_repos_dir_with_data)
        repos = ops.list_repos()

        assert len(repos) == 2
        assert any(r["alias"] == "repo1-global" for r in repos)
        assert any(r["alias"] == "repo2-global" for r in repos)

        # Verify structure (API-normalized field names)
        repo = repos[0]
        assert "repo_name" in repo
        assert "alias" in repo
        assert "url" in repo
        assert "last_refresh" in repo

    def test_list_repos_empty_registry(self, temp_golden_repos_dir):
        """Test that list_repos returns empty list for empty registry."""
        ops = GlobalRepoOperations(temp_golden_repos_dir)
        repos = ops.list_repos()

        assert repos == []

    def test_list_repos_with_filters_placeholder(self, golden_repos_dir_with_data):
        """Test that list_repos accepts filters parameter (for future use)."""
        ops = GlobalRepoOperations(golden_repos_dir_with_data)

        # Should not raise error even with filters=None
        repos = ops.list_repos(filters=None)
        assert len(repos) == 2


class TestGetStatus:
    """Tests for get_status functionality."""

    def test_get_status_returns_repo_metadata(self, golden_repos_dir_with_data):
        """Test that get_status returns metadata for existing repo."""
        ops = GlobalRepoOperations(golden_repos_dir_with_data)
        status = ops.get_status("repo1-global")

        assert status["alias"] == "repo1-global"
        assert status["repo_name"] == "repo1"
        assert status["url"] == "https://github.com/test/repo1.git"
        assert "last_refresh" in status

    def test_get_status_raises_for_nonexistent_repo(self, temp_golden_repos_dir):
        """Test that get_status raises ValueError for non-existent repo."""
        ops = GlobalRepoOperations(temp_golden_repos_dir)

        with pytest.raises(ValueError, match="Global repo 'nonexistent-global' not found"):
            ops.get_status("nonexistent-global")

    def test_get_status_includes_all_metadata_fields(self, golden_repos_dir_with_data):
        """Test that get_status includes all required metadata fields."""
        ops = GlobalRepoOperations(golden_repos_dir_with_data)
        status = ops.get_status("repo2-global")

        required_fields = [
            "alias", "repo_name", "url", "last_refresh"
        ]

        for field in required_fields:
            assert field in status, f"Missing required field: {field}"


class TestGetConfig:
    """Tests for get_config functionality."""

    def test_get_config_returns_refresh_interval(self, temp_golden_repos_dir):
        """Test that get_config returns refresh interval."""
        # Create config file with test data
        config_file = Path(temp_golden_repos_dir) / "global_config.json"
        test_config = {"refresh_interval": 3600}
        config_file.write_text(json.dumps(test_config))

        ops = GlobalRepoOperations(temp_golden_repos_dir)
        config = ops.get_config()

        assert "refresh_interval" in config
        assert config["refresh_interval"] == 3600

    def test_get_config_creates_default_if_not_exists(self, temp_golden_repos_dir):
        """Test that get_config creates default config if file doesn't exist."""
        ops = GlobalRepoOperations(temp_golden_repos_dir)
        config = ops.get_config()

        assert "refresh_interval" in config
        assert config["refresh_interval"] == 3600  # Default value

        # Verify file was created
        config_file = Path(temp_golden_repos_dir) / "global_config.json"
        assert config_file.exists()

    def test_get_config_handles_corrupted_file(self, temp_golden_repos_dir):
        """Test that get_config handles corrupted config file gracefully."""
        # Create corrupted config file
        config_file = Path(temp_golden_repos_dir) / "global_config.json"
        config_file.write_text("not valid json {{{")

        ops = GlobalRepoOperations(temp_golden_repos_dir)
        config = ops.get_config()

        # Should return default config
        assert config["refresh_interval"] == 3600


class TestSetConfig:
    """Tests for set_config functionality."""

    def test_set_config_validates_minimum_60_seconds(self, temp_golden_repos_dir):
        """Test that set_config validates minimum refresh interval of 60 seconds."""
        ops = GlobalRepoOperations(temp_golden_repos_dir)

        # Should raise ValueError for values < 60
        with pytest.raises(ValueError, match="Refresh interval must be at least 60 seconds"):
            ops.set_config(59)

        with pytest.raises(ValueError, match="Refresh interval must be at least 60 seconds"):
            ops.set_config(30)

        with pytest.raises(ValueError, match="Refresh interval must be at least 60 seconds"):
            ops.set_config(0)

        with pytest.raises(ValueError, match="Refresh interval must be at least 60 seconds"):
            ops.set_config(-100)

    def test_set_config_accepts_valid_values(self, temp_golden_repos_dir):
        """Test that set_config accepts values >= 60."""
        ops = GlobalRepoOperations(temp_golden_repos_dir)

        # Should not raise error
        ops.set_config(60)  # Minimum
        ops.set_config(3600)  # 1 hour
        ops.set_config(86400)  # 1 day

    def test_set_config_persists_to_file(self, temp_golden_repos_dir):
        """Test that set_config persists configuration to file."""
        ops = GlobalRepoOperations(temp_golden_repos_dir)

        # Set config
        ops.set_config(7200)

        # Verify file was written
        config_file = Path(temp_golden_repos_dir) / "global_config.json"
        assert config_file.exists()

        # Verify content
        with open(config_file, "r") as f:
            config_data = json.load(f)

        assert config_data["refresh_interval"] == 7200

    def test_set_config_uses_atomic_write(self, temp_golden_repos_dir):
        """Test that set_config uses atomic write pattern."""
        ops = GlobalRepoOperations(temp_golden_repos_dir)

        # Set initial config
        ops.set_config(3600)

        # Set new config
        ops.set_config(7200)

        # Read config file directly
        config_file = Path(temp_golden_repos_dir) / "global_config.json"
        with open(config_file, "r") as f:
            config_data = json.load(f)

        # Should have new value (atomic write succeeded)
        assert config_data["refresh_interval"] == 7200

        # Verify no temp files left behind
        temp_files = list(Path(temp_golden_repos_dir).glob(".global_config_*.tmp"))
        assert len(temp_files) == 0

    def test_set_config_roundtrip(self, temp_golden_repos_dir):
        """Test that set_config + get_config roundtrip works correctly."""
        ops = GlobalRepoOperations(temp_golden_repos_dir)

        # Set config
        ops.set_config(5400)

        # Get config
        config = ops.get_config()

        assert config["refresh_interval"] == 5400


class TestGlobalRepoOperationsInitialization:
    """Tests for GlobalRepoOperations initialization."""

    def test_initialization_creates_directory_structure(self):
        """Test that initialization creates necessary directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_dir = Path(tmpdir) / "golden-repos"

            # Directory should not exist yet
            assert not golden_dir.exists()

            # Initialize
            ops = GlobalRepoOperations(str(golden_dir))

            # Directory should now exist
            assert golden_dir.exists()
            assert (golden_dir / "aliases").exists()
            assert (golden_dir / "global_registry.json").exists()

    def test_initialization_with_existing_directory(self, temp_golden_repos_dir):
        """Test that initialization works with existing directory."""
        # Should not raise error
        ops = GlobalRepoOperations(temp_golden_repos_dir)

        # Verify directories still exist
        golden_dir = Path(temp_golden_repos_dir)
        assert golden_dir.exists()
        assert (golden_dir / "aliases").exists()

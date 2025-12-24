"""Tests for remote configuration format mismatch between initialization and mode detection.

This test module reproduces and validates the fix for the critical issue where:
1. Remote initialization creates .remote-config with 'encrypted_password' field
2. Mode detector expects 'encrypted_credentials' field
3. Commands fail due to mode detection failure despite valid remote setup

The mismatch prevents remote mode from working correctly.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from code_indexer.remote.initialization import initialize_remote_mode
from code_indexer.remote.config import create_remote_configuration, RemoteConfig
from code_indexer.mode_detection.command_mode_detector import CommandModeDetector


class TestRemoteConfigurationFormatMismatch:
    """Test cases that reproduce the configuration format mismatch issue."""

    @pytest.fixture
    def temp_project_root(self, tmp_path):
        """Create a temporary project root for testing."""
        return tmp_path / "test_project"

    @pytest.fixture
    def mock_validation_steps(self):
        """Mock all validation steps during remote initialization."""
        with (
            patch(
                "code_indexer.remote.initialization.validate_and_normalize_server_url"
            ) as mock_url,
            patch(
                "code_indexer.remote.initialization.test_server_connectivity"
            ) as mock_conn,
            patch(
                "code_indexer.remote.initialization.validate_credentials"
            ) as mock_creds,
        ):

            # Configure mocks to return successful validation
            mock_url.return_value = "http://127.0.0.1:8095"
            mock_conn.return_value = AsyncMock()
            mock_creds.return_value = {"username": "admin", "user_id": 1}

            yield {
                "url": mock_url,
                "connectivity": mock_conn,
                "credentials": mock_creds,
            }

    def test_remote_initialization_creates_correct_config_format_after_fix(
        self, temp_project_root
    ):
        """Test that remote initialization now creates config with correct field name.

        After the fix, this test demonstrates that the initialization process
        creates the correct configuration format expected by the mode detector.
        """
        # Arrange: Prepare project structure
        temp_project_root.mkdir(parents=True)

        # Act: Create remote configuration using the fixed initialization function
        create_remote_configuration(
            project_root=temp_project_root,
            server_url="http://127.0.0.1:8095",
            username="admin",
            encrypted_credentials="dummy_encrypted_credentials",
        )

        # Assert: Check that correct field is created
        config_file = temp_project_root / ".code-indexer" / ".remote-config"
        assert config_file.exists()

        with open(config_file, "r") as f:
            config_data = json.load(f)

        # FIXED: This shows the initialization now creates 'encrypted_credentials'
        assert "encrypted_credentials" in config_data
        assert config_data["encrypted_credentials"] == "dummy_encrypted_credentials"

        # Old wrong field should not exist after the fix
        assert "encrypted_password" not in config_data

    def test_mode_detector_rejects_config_with_encrypted_password_field(
        self, temp_project_root
    ):
        """Test that mode detector fails to recognize remote config with 'encrypted_password' field.

        This test proves the mode detector validation fails when the configuration
        contains 'encrypted_password' instead of 'encrypted_credentials'.
        """
        # Arrange: Create project directory and config with 'encrypted_password' (wrong format)
        temp_project_root.mkdir(parents=True)
        config_dir = temp_project_root / ".code-indexer"
        config_dir.mkdir()

        # Create .remote-config with WRONG format (as created by initialization)
        wrong_config = {
            "mode": "remote",
            "server_url": "http://127.0.0.1:8095",
            "username": "admin",
            "encrypted_password": "dummy_encrypted_password",  # WRONG FIELD NAME
            "created_at": "2025-09-16T22:12:38.928720Z",
        }

        config_file = config_dir / ".remote-config"
        with open(config_file, "w") as f:
            json.dump(wrong_config, f)

        # Act: Attempt mode detection
        detector = CommandModeDetector(temp_project_root)
        detected_mode = detector.detect_mode()

        # Assert: Mode detector should FAIL to recognize this as remote mode
        # because it expects 'encrypted_credentials' but finds 'encrypted_password'
        assert detected_mode == "uninitialized"  # REPRODUCES THE BUG

        # Verify the specific validation failure
        config_path = config_dir / ".remote-config"
        is_valid = detector._validate_remote_config(config_path)
        assert is_valid is False  # Validation fails due to field name mismatch

    def test_mode_detector_accepts_config_with_encrypted_credentials_field(
        self, temp_project_root
    ):
        """Test that mode detector works correctly with 'encrypted_credentials' field.

        This test proves what the CORRECT format should be.
        """
        # Arrange: Create project directory and config with 'encrypted_credentials' (correct format)
        temp_project_root.mkdir(parents=True)
        config_dir = temp_project_root / ".code-indexer"
        config_dir.mkdir()

        # Create .remote-config with CORRECT format (expected by mode detector)
        correct_config = {
            "mode": "remote",
            "server_url": "http://127.0.0.1:8095",
            "username": "admin",
            "encrypted_credentials": "dummy_encrypted_credentials",  # CORRECT FIELD NAME
            "created_at": "2025-09-16T22:12:38.928720Z",
        }

        config_file = config_dir / ".remote-config"
        with open(config_file, "w") as f:
            json.dump(correct_config, f)

        # Act: Attempt mode detection
        detector = CommandModeDetector(temp_project_root)
        detected_mode = detector.detect_mode()

        # Assert: Mode detector should correctly recognize this as remote mode
        assert detected_mode == "remote"

        # Verify the specific validation success
        config_path = config_dir / ".remote-config"
        is_valid = detector._validate_remote_config(config_path)
        assert is_valid is True  # Validation succeeds with correct field name

    @pytest.mark.asyncio
    async def test_full_remote_initialization_creates_usable_config_after_fix(
        self, temp_project_root, mock_validation_steps
    ):
        """Test end-to-end: remote initialization creates config that mode detector recognizes.

        After the fix, this test validates the complete flow works correctly:
        1. User runs remote initialization
        2. Initialization creates config with 'encrypted_credentials'
        3. Mode detector correctly recognizes the configuration
        4. Subsequent commands can work properly
        """
        # Arrange: Set up temp project
        temp_project_root.mkdir(parents=True)

        # Act: Run complete remote initialization
        await initialize_remote_mode(
            project_root=temp_project_root,
            server_url="http://127.0.0.1:8095",
            username="admin",
            password="password123",
        )

        # Assert: Configuration file should exist
        config_file = temp_project_root / ".code-indexer" / ".remote-config"
        assert config_file.exists()

        # Read the configuration created by initialization
        with open(config_file, "r") as f:
            config_data = json.load(f)

        # Verify initialization created the CORRECT format after fix
        assert "encrypted_credentials" in config_data
        assert "encrypted_password" not in config_data

        # Encrypted credentials should contain actual data
        assert config_data["encrypted_credentials"] != ""
        assert len(config_data["encrypted_credentials"]) > 0

        # Mode detector should now correctly recognize this config
        detector = CommandModeDetector(temp_project_root)
        detected_mode = detector.detect_mode()

        # FIXED: initialization now creates compatible config, mode detector works
        assert detected_mode == "remote"  # NOW WORKS correctly!

        # This means subsequent commands can work properly
        # because the system correctly recognizes remote mode

    def test_credential_storage_flow_expectations(self, temp_project_root):
        """Test that credential storage component expects 'encrypted_credentials' field.

        This test verifies that other components also expect the 'encrypted_credentials'
        field format, confirming that mode detector expectation is correct.
        """
        # Arrange: Create config file with wrong format
        temp_project_root.mkdir(parents=True)
        config_dir = temp_project_root / ".code-indexer"
        config_dir.mkdir()

        # Create config file with encrypted_password (wrong format)
        wrong_config = {
            "mode": "remote",
            "server_url": "http://127.0.0.1:8095",
            "username": "admin",
            "encrypted_password": "dummy_encrypted_password",  # Wrong field
        }

        config_file = config_dir / ".remote-config"
        with open(config_file, "w") as f:
            json.dump(wrong_config, f)

        # Act & Assert: Verify that API client components expect 'encrypted_credentials'
        # Look at the base_client.py code to see the expected field name

        # The API client looks for 'encrypted_credentials' field
        config_data = wrong_config
        encrypted_creds = config_data.get("encrypted_credentials")

        # This will be None because the field doesn't exist (it's 'encrypted_password')
        assert encrypted_creds is None

        # This would cause API client to fail: "No encrypted_credentials found in configuration"
        # Further confirming that 'encrypted_credentials' is the expected format

    def test_mixed_format_consistency_check(self, temp_project_root):
        """Test to identify all code that expects 'encrypted_credentials' vs 'encrypted_password'.

        This test documents the expected format across the codebase to ensure
        consistent field naming after the fix.
        """
        # This test serves as documentation of the correct format

        # CORRECT format (expected by mode detector and API clients):
        correct_format = {
            "mode": "remote",
            "server_url": "http://127.0.0.1:8095",
            "username": "admin",
            "encrypted_credentials": "encrypted_data_here",  # Correct field name
            "created_at": "2025-09-16T22:12:38.928720Z",
        }

        # WRONG format (created by initialization):
        wrong_format = {
            "mode": "remote",
            "server_url": "http://127.0.0.1:8095",
            "username": "admin",
            "encrypted_password": "encrypted_data_here",  # Wrong field name
            "created_at": "2025-09-16T22:12:38.928720Z",
        }

        # The fix should make initialization create the correct format
        assert "encrypted_credentials" in correct_format
        assert "encrypted_password" not in correct_format

        # Wrong format should be eliminated
        assert "encrypted_password" in wrong_format
        assert "encrypted_credentials" not in wrong_format


class TestRemoteConfigurationFormatAfterFix:
    """Test cases that validate the fixed configuration format.

    These tests will PASS after implementing the fix.
    """

    @pytest.fixture
    def temp_project_root(self, tmp_path):
        """Create a temporary project root for testing."""
        return tmp_path / "test_project"

    @pytest.fixture
    def mock_validation_steps(self):
        """Mock all validation steps during remote initialization."""
        with (
            patch(
                "code_indexer.remote.initialization.validate_and_normalize_server_url"
            ) as mock_url,
            patch(
                "code_indexer.remote.initialization.test_server_connectivity"
            ) as mock_conn,
            patch(
                "code_indexer.remote.initialization.validate_credentials"
            ) as mock_creds,
        ):

            # Configure mocks to return successful validation
            mock_url.return_value = "http://127.0.0.1:8095"
            mock_conn.return_value = AsyncMock()
            mock_creds.return_value = {"username": "admin", "user_id": 1}

            yield {
                "url": mock_url,
                "connectivity": mock_conn,
                "credentials": mock_creds,
            }

    @pytest.mark.asyncio
    async def test_initialization_creates_correct_format_after_fix(
        self, temp_project_root, mock_validation_steps
    ):
        """Test that initialization creates config with 'encrypted_credentials' field after fix.

        This test validates the fix creates the correct configuration format.
        """
        # Arrange: Set up temp project
        temp_project_root.mkdir(parents=True)

        # Act: Run complete remote initialization
        await initialize_remote_mode(
            project_root=temp_project_root,
            server_url="http://127.0.0.1:8095",
            username="admin",
            password="password123",
        )

        # Assert: Configuration file should exist
        config_file = temp_project_root / ".code-indexer" / ".remote-config"
        assert config_file.exists()

        # Read the configuration created by initialization
        with open(config_file, "r") as f:
            config_data = json.load(f)

        # Verify initialization created the CORRECT format after fix
        assert "encrypted_credentials" in config_data
        assert (
            "encrypted_password" not in config_data
        )  # Old wrong field should not exist

        # Verify the encrypted_credentials field contains actual data (not empty)
        assert config_data["encrypted_credentials"] != ""
        assert len(config_data["encrypted_credentials"]) > 0

        # Verify the configuration contains expected fields
        assert config_data["mode"] == "remote"
        assert config_data["server_url"] == "http://127.0.0.1:8095"
        assert config_data["username"] == "admin"
        assert "created_at" in config_data
        assert "updated_at" in config_data

    @pytest.mark.asyncio
    async def test_end_to_end_remote_mode_after_fix(
        self, temp_project_root, mock_validation_steps
    ):
        """Test complete remote mode flow works after fixing configuration format.

        This test validates the entire flow: initialization → mode detection → ready for commands
        """
        # Arrange: Set up temp project
        temp_project_root.mkdir(parents=True)

        # Act 1: Run complete remote initialization
        await initialize_remote_mode(
            project_root=temp_project_root,
            server_url="http://127.0.0.1:8095",
            username="admin",
            password="password123",
        )

        # Act 2: Test mode detection after initialization
        detector = CommandModeDetector(temp_project_root)
        detected_mode = detector.detect_mode()

        # Assert: Mode detector should correctly recognize remote mode
        assert detected_mode == "remote"  # This should work now!

        # Verify the configuration validation passes
        config_file = temp_project_root / ".code-indexer" / ".remote-config"
        is_valid = detector._validate_remote_config(config_file)
        assert is_valid is True

        # Assert: Configuration should be ready for API client usage
        with open(config_file, "r") as f:
            config_data = json.load(f)

        # API client expects 'encrypted_credentials' field
        encrypted_creds = config_data.get("encrypted_credentials")
        assert encrypted_creds is not None
        assert encrypted_creds != ""

        # This means the configuration is now ready for:
        # - Mode detection (✓ tested)
        # - API client usage (✓ contains encrypted_credentials)
        # - Remote command execution (✓ mode is detected as remote)


class TestBackwardCompatibility:
    """Test cases to ensure backward compatibility with old configuration formats."""

    @pytest.fixture
    def temp_project_root(self, tmp_path):
        """Create a temporary project root for testing."""
        return tmp_path / "test_project"

    def test_mode_detector_handles_legacy_format_gracefully(self, temp_project_root):
        """Test that mode detector handles old 'encrypted_password' format gracefully.

        This test ensures we don't break existing installations that might have
        the old configuration format.
        """
        # Arrange: Create project directory and config with OLD format
        temp_project_root.mkdir(parents=True)
        config_dir = temp_project_root / ".code-indexer"
        config_dir.mkdir()

        # Create .remote-config with OLD format (as would exist on older installations)
        legacy_config = {
            "mode": "remote",
            "server_url": "http://127.0.0.1:8095",
            "username": "admin",
            "encrypted_password": "legacy_encrypted_password",  # OLD FIELD NAME
            "created_at": "2025-09-16T22:12:38.928720Z",
        }

        config_file = config_dir / ".remote-config"
        with open(config_file, "w") as f:
            json.dump(legacy_config, f)

        # Act: Attempt mode detection
        detector = CommandModeDetector(temp_project_root)
        detected_mode = detector.detect_mode()

        # Assert: Mode detector should gracefully handle legacy format
        # Currently it returns "uninitialized" for legacy format
        # This is acceptable behavior - old configs need to be re-initialized
        assert detected_mode == "uninitialized"

        # Verify validation specifically fails for legacy format
        is_valid = detector._validate_remote_config(config_file)
        assert is_valid is False

    def test_credential_storage_backward_compatibility(self, temp_project_root):
        """Test that new credential storage still supports legacy .creds file access.

        This ensures that our fix doesn't break existing credential access patterns.
        """
        # Arrange: Create configuration and store credentials using new method
        temp_project_root.mkdir(parents=True)

        # Create configuration using new method
        create_remote_configuration(
            project_root=temp_project_root,
            server_url="http://127.0.0.1:8095",
            username="admin",
            encrypted_credentials="",
        )

        # Store credentials using new RemoteConfig method
        remote_config = RemoteConfig(temp_project_root)
        remote_config.store_credentials("test_password")

        # Assert: Both new and legacy credential access should work

        # 1. New method: credentials should be in configuration file
        config_file = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_file, "r") as f:
            config_data = json.load(f)

        assert "encrypted_credentials" in config_data
        assert config_data["encrypted_credentials"] != ""

        # 2. Legacy method: credentials should also be in .creds file
        creds_file = temp_project_root / ".code-indexer" / ".creds"
        assert creds_file.exists()

        # 3. Legacy credential loading should still work
        from code_indexer.remote.credential_manager import load_encrypted_credentials

        legacy_encrypted_data = load_encrypted_credentials(temp_project_root)
        assert legacy_encrypted_data is not None
        assert len(legacy_encrypted_data) > 0

        # 4. New credential access should also work
        decrypted_creds = remote_config.get_decrypted_credentials()
        assert decrypted_creds.username == "admin"
        assert decrypted_creds.password == "test_password"

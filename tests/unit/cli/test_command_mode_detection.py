"""Test module for Command Mode Detection functionality.

Tests the automatic detection of local, remote, and uninitialized modes
based on configuration file presence and validation.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


from code_indexer.mode_detection.command_mode_detector import (
    CommandModeDetector,
    find_project_root,
    ModeDetectionError,
)


class TestCommandModeDetector:
    """Test class for CommandModeDetector functionality."""

    def test_detect_mode_returns_literal_type(self):
        """Test that detect_mode returns proper Literal type."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            detector = CommandModeDetector(project_root)

            # Should fail initially as class doesn't exist yet
            mode = detector.detect_mode()
            assert mode in ["local", "remote", "uninitialized"]

    def test_detect_uninitialized_mode_no_config_dir(self):
        """Test detection of uninitialized mode when no .code-indexer directory exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            detector = CommandModeDetector(project_root)

            mode = detector.detect_mode()
            assert mode == "uninitialized"

    def test_detect_uninitialized_mode_empty_config_dir(self):
        """Test detection of uninitialized mode when .code-indexer directory is empty."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            detector = CommandModeDetector(project_root)
            mode = detector.detect_mode()
            assert mode == "uninitialized"

    def test_detect_local_mode_with_valid_local_config(self):
        """Test detection of local mode with valid local configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid local config.json
            config_data = {
                "ollama": {
                    "host": "http://localhost:11434",
                    "model": "nomic-embed-text",
                },
                "qdrant": {"host": "http://localhost:6333"},
                "ports": {"ollama_port": 11434, "qdrant_port": 6333},
            }
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            detector = CommandModeDetector(project_root)
            mode = detector.detect_mode()
            assert mode == "local"

    def test_detect_remote_mode_with_valid_remote_config(self):
        """Test detection of remote mode with valid remote configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid remote config
            remote_config_data = {
                "server_url": "https://server.example.com",
                "encrypted_credentials": "encrypted_data_here",
                "repository_link": {
                    "alias": "test-repo",
                    "url": "https://github.com/test/repo.git",
                },
            }
            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config_data, f)

            detector = CommandModeDetector(project_root)
            mode = detector.detect_mode()
            assert mode == "remote"

    def test_remote_mode_takes_precedence_over_local(self):
        """Test that remote config takes precedence when both local and remote configs exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create both local and remote configs
            local_config_data = {
                "ollama": {"host": "http://localhost:11434"},
                "qdrant": {"host": "http://localhost:6333"},
            }
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(local_config_data, f)

            remote_config_data = {
                "server_url": "https://server.example.com",
                "encrypted_credentials": "encrypted_data_here",
            }
            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config_data, f)

            detector = CommandModeDetector(project_root)
            mode = detector.detect_mode()
            assert mode == "remote"

    def test_validate_remote_config_missing_required_fields(self):
        """Test validation of remote config with missing required fields."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create invalid remote config missing server_url
            remote_config_data = {"encrypted_credentials": "encrypted_data_here"}
            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config_data, f)

            detector = CommandModeDetector(project_root)
            is_valid = detector._validate_remote_config(remote_config_path)
            assert is_valid is False

    def test_validate_remote_config_with_all_required_fields(self):
        """Test validation of remote config with all required fields."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid remote config with all required fields
            remote_config_data = {
                "server_url": "https://server.example.com",
                "encrypted_credentials": "encrypted_data_here",
                "repository_link": {
                    "alias": "test",
                    "url": "https://github.com/test/repo.git",
                },
            }
            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config_data, f)

            detector = CommandModeDetector(project_root)
            is_valid = detector._validate_remote_config(remote_config_path)
            assert is_valid is True

    def test_validate_local_config_invalid_json(self):
        """Test validation of local config with invalid JSON."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create invalid JSON file
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                f.write("invalid json content {")

            detector = CommandModeDetector(project_root)
            is_valid = detector._validate_local_config(config_path)
            assert is_valid is False

    def test_validate_local_config_valid_json(self):
        """Test validation of local config with valid JSON."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid JSON file
            config_data = {"ollama": {"host": "http://localhost:11434"}}
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            detector = CommandModeDetector(project_root)
            is_valid = detector._validate_local_config(config_path)
            assert is_valid is True

    def test_detect_mode_handles_file_permission_errors(self):
        """Test that mode detection handles file permission errors gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create a file but make it unreadable
            config_path = config_dir / "config.json"
            config_path.write_text("{}")
            config_path.chmod(0o000)  # Remove all permissions

            try:
                detector = CommandModeDetector(project_root)
                mode = detector.detect_mode()
                # Should fall back to uninitialized when configs are unreadable
                assert mode == "uninitialized"
            finally:
                # Restore permissions for cleanup
                config_path.chmod(0o644)

    def test_detect_mode_with_corrupted_remote_config_falls_back_to_local(self):
        """Test that corrupted remote config falls back to local mode if valid local config exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid local config
            local_config_data = {
                "ollama": {"host": "http://localhost:11434"},
                "qdrant": {"host": "http://localhost:6333"},
            }
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(local_config_data, f)

            # Create corrupted remote config
            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                f.write("corrupted json {")

            detector = CommandModeDetector(project_root)
            mode = detector.detect_mode()
            assert mode == "local"


class TestFindProjectRoot:
    """Test class for project root discovery functionality."""

    def test_find_project_root_from_current_directory(self):
        """Test finding project root when .code-indexer is in current directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            found_root = find_project_root(project_root)
            assert found_root == project_root

    def test_find_project_root_walking_up_tree(self):
        """Test finding project root by walking up directory tree."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create nested subdirectory
            nested_dir = project_root / "src" / "module" / "submodule"
            nested_dir.mkdir(parents=True)

            found_root = find_project_root(nested_dir)
            assert found_root == project_root

    def test_find_project_root_stops_at_first_match(self):
        """Test that project root discovery stops at first .code-indexer directory found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested project structure
            outer_project = Path(temp_dir)
            outer_config = outer_project / ".code-indexer"
            outer_config.mkdir()

            inner_project = outer_project / "subproject"
            inner_project.mkdir()
            inner_config = inner_project / ".code-indexer"
            inner_config.mkdir()

            nested_dir = inner_project / "src"
            nested_dir.mkdir()

            # Should find inner project, not outer
            found_root = find_project_root(nested_dir)
            assert found_root == inner_project

    def test_find_project_root_no_config_returns_start_path(self):
        """Test that project root discovery returns start path when no .code-indexer found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a structure deep enough that we exceed the 10-level search limit
            # This ensures we don't accidentally find an existing .code-indexer directory
            deep_path = Path(temp_dir)
            for i in range(12):  # Create 12 levels deep
                deep_path = deep_path / f"level{i}"
            deep_path.mkdir(parents=True)
            start_path = deep_path / "src"
            start_path.mkdir()

            found_root = find_project_root(start_path)
            assert found_root == start_path

    def test_find_project_root_handles_permission_errors(self):
        """Test that project root discovery handles permission errors gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a deeper nested structure to avoid finding /tmp/.code-indexer
            base_path = Path(temp_dir) / "isolated" / "project" / "deep" / "nested"
            base_path.mkdir(parents=True)
            start_path = base_path / "src"
            start_path.mkdir()

            # Mock permission error during directory walking
            with patch(
                "pathlib.Path.exists", side_effect=PermissionError("Permission denied")
            ):
                found_root = find_project_root(start_path)
                # Should fallback to start path
                assert found_root == start_path

    def test_find_project_root_with_broken_symlinks(self):
        """Test that project root discovery handles broken symbolic links."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create broken symlink
            broken_link = project_root / "broken_link"
            broken_link.symlink_to("nonexistent_target")

            nested_dir = project_root / "src"
            nested_dir.mkdir()

            found_root = find_project_root(nested_dir)
            assert found_root == project_root


class TestModeDetectionError:
    """Test class for ModeDetectionError exception."""

    def test_mode_detection_error_inheritance(self):
        """Test that ModeDetectionError inherits from Exception."""
        error = ModeDetectionError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_mode_detection_error_with_cause(self):
        """Test ModeDetectionError with underlying cause."""
        original_error = ValueError("Original error")
        try:
            raise ModeDetectionError(
                "Configuration validation failed"
            ) from original_error
        except ModeDetectionError as wrapped_error:
            assert isinstance(wrapped_error, ModeDetectionError)
            assert wrapped_error.__cause__ == original_error

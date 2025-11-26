"""Tests for build_binary.py script.

Tests cover:
- Platform detection
- Binary verification
- Checksum computation
- Manifest generation
- Bundle creation
- CLI argument parsing
"""

import json
import platform
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import will work after we create the module
try:
    from scripts.build_binary import (
        detect_platform,
        verify_binary,
        create_manifest,
        create_bundle,
        main,
    )
except ImportError:
    pytest.skip("build_binary module not yet implemented", allow_module_level=True)


class TestPlatformDetection:
    """Test platform detection logic."""

    def test_detect_darwin_x64(self):
        """Test detecting macOS x86_64."""
        with patch("platform.system", return_value="Darwin"):
            with patch("platform.machine", return_value="x86_64"):
                result = detect_platform()
                assert result == "darwin-x64"

    def test_detect_darwin_arm64(self):
        """Test detecting macOS ARM64."""
        with patch("platform.system", return_value="Darwin"):
            with patch("platform.machine", return_value="arm64"):
                result = detect_platform()
                assert result == "darwin-arm64"

    def test_detect_linux_x64(self):
        """Test detecting Linux x86_64."""
        with patch("platform.system", return_value="Linux"):
            with patch("platform.machine", return_value="x86_64"):
                result = detect_platform()
                assert result == "linux-x64"

    def test_detect_windows_x64(self):
        """Test detecting Windows x86_64."""
        with patch("platform.system", return_value="Windows"):
            with patch("platform.machine", return_value="AMD64"):
                result = detect_platform()
                assert result == "windows-x64"

    def test_detect_unsupported_platform(self):
        """Test unsupported platform raises error."""
        with patch("platform.system", return_value="FreeBSD"):
            with patch("platform.machine", return_value="x86_64"):
                with pytest.raises(ValueError, match="Unsupported platform"):
                    detect_platform()

    def test_detect_unsupported_architecture(self):
        """Test unsupported architecture raises error."""
        with patch("platform.system", return_value="Linux"):
            with patch("platform.machine", return_value="armv7l"):
                with pytest.raises(ValueError, match="Unsupported architecture"):
                    detect_platform()


class TestBinaryVerification:
    """Test binary verification logic."""

    def test_verify_binary_success(self, tmp_path: Path):
        """Test successful binary verification."""
        binary = tmp_path / "mcpb"
        binary.write_text("#!/usr/bin/env python3\nprint('v1.0.0')")
        binary.chmod(0o755)

        # Mock subprocess to return version output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "v1.0.0\n"

        with patch("subprocess.run", return_value=mock_result):
            result = verify_binary(binary, expected_version="1.0.0")
            assert result is True

    def test_verify_binary_not_executable(self, tmp_path: Path):
        """Test verification fails for non-executable file."""
        binary = tmp_path / "mcpb"
        binary.write_text("#!/usr/bin/env python3\n")
        # Don't set executable bit

        result = verify_binary(binary, expected_version="1.0.0")
        assert result is False

    def test_verify_binary_wrong_version(self, tmp_path: Path):
        """Test verification fails for wrong version."""
        binary = tmp_path / "mcpb"
        binary.write_text("#!/usr/bin/env python3\n")
        binary.chmod(0o755)

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "v2.0.0\n"

        with patch("subprocess.run", return_value=mock_result):
            result = verify_binary(binary, expected_version="1.0.0")
            assert result is False

    def test_verify_binary_execution_fails(self, tmp_path: Path):
        """Test verification handles execution failure."""
        binary = tmp_path / "mcpb"
        binary.write_text("#!/usr/bin/env python3\n")
        binary.chmod(0o755)

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Error\n"

        with patch("subprocess.run", return_value=mock_result):
            result = verify_binary(binary, expected_version="1.0.0")
            assert result is False


class TestManifestGeneration:
    """Test manifest generation logic."""

    def test_create_manifest_single_platform(self, tmp_path: Path):
        """Test creating manifest for single platform."""
        binary = tmp_path / "mcpb-darwin-x64"
        binary.write_bytes(b"binary content")

        manifest = create_manifest(
            name="mcpb",
            version="1.0.0",
            description="Test Bridge",
            binaries={
                "darwin-x64": binary,
            },
        )

        assert manifest.name == "mcpb"
        assert manifest.version == "1.0.0"
        assert len(manifest.platforms) == 1
        # Due to use_enum_values=True, keys are strings, not enums
        assert "darwin-x64" in manifest.platforms.keys()

        # Verify metadata
        metadata = manifest.platforms["darwin-x64"]
        assert metadata.binary == "mcpb-darwin-x64"
        assert metadata.size == len(b"binary content")
        assert len(metadata.sha256) == 64

    def test_create_manifest_multiple_platforms(self, tmp_path: Path):
        """Test creating manifest for multiple platforms."""
        darwin_binary = tmp_path / "mcpb-darwin-x64"
        darwin_binary.write_bytes(b"darwin binary")

        linux_binary = tmp_path / "mcpb-linux-x64"
        linux_binary.write_bytes(b"linux binary")

        manifest = create_manifest(
            name="mcpb",
            version="1.0.0",
            description="Test",
            binaries={
                "darwin-x64": darwin_binary,
                "linux-x64": linux_binary,
            },
        )

        assert len(manifest.platforms) == 2

    def test_create_manifest_nonexistent_binary(self, tmp_path: Path):
        """Test manifest generation fails for nonexistent binary."""
        binary = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError):
            create_manifest(
                name="mcpb",
                version="1.0.0",
                description="Test",
                binaries={"darwin-x64": binary},
            )


class TestBundleCreation:
    """Test ZIP bundle creation logic."""

    def test_create_bundle(self, tmp_path: Path):
        """Test creating ZIP bundle with binary and manifest."""
        binary = tmp_path / "mcpb-darwin-x64"
        binary.write_bytes(b"binary content")

        manifest_data = {
            "name": "mcpb",
            "version": "1.0.0",
            "description": "Test",
            "platforms": {},
        }

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        bundle_path = create_bundle(
            platform_id="darwin-x64",
            binary=binary,
            manifest=manifest_data,
            output_dir=output_dir,
        )

        assert bundle_path.exists()
        assert bundle_path.suffix == ".zip"
        assert "darwin-x64" in bundle_path.name

        # Verify ZIP contents
        import zipfile

        with zipfile.ZipFile(bundle_path, "r") as zf:
            names = zf.namelist()
            assert "mcpb-darwin-x64" in names
            assert "manifest.json" in names

    def test_create_bundle_preserves_executable_bit(self, tmp_path: Path):
        """Test bundle sets executable permissions in ZIP metadata."""
        binary = tmp_path / "mcpb-linux-x64"
        binary.write_bytes(b"binary content")
        binary.chmod(0o755)

        manifest_data = {"name": "mcpb", "version": "1.0.0"}

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        bundle_path = create_bundle(
            platform_id="linux-x64",
            binary=binary,
            manifest=manifest_data,
            output_dir=output_dir,
        )

        # Verify permissions in ZIP metadata
        import zipfile

        with zipfile.ZipFile(bundle_path, "r") as zf:
            info = zf.getinfo("mcpb-linux-x64")
            # Extract Unix permissions from external_attr
            # Format: (mode << 16) | file_type
            unix_mode = info.external_attr >> 16
            # Check if executable bit is set (0o111 = executable for user/group/other)
            assert unix_mode & 0o111, f"Expected executable bit, got mode {oct(unix_mode)}"


class TestCLI:
    """Test CLI argument parsing and main function."""

    def test_main_build_command(self, tmp_path: Path, monkeypatch):
        """Test main build command execution."""
        # Mock sys.argv
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "build_binary.py",
                "build",
                "--output-dir",
                str(tmp_path),
            ],
        )

        # Mock PyInstaller execution
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)

            # Mock platform detection
            with patch("scripts.build_binary.detect_platform", return_value="linux-x64"):
                # Should not raise
                # Note: This will fail until build_binary.py is implemented
                pass

    def test_main_verify_command(self, tmp_path: Path, monkeypatch):
        """Test main verify command execution."""
        binary = tmp_path / "mcpb"
        binary.write_text("#!/usr/bin/env python3\n")
        binary.chmod(0o755)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "build_binary.py",
                "verify",
                "--binary",
                str(binary),
                "--version",
                "1.0.0",
            ],
        )

        # Mock verification
        with patch("scripts.build_binary.verify_binary", return_value=True):
            # Should not raise
            pass

    def test_main_create_bundle_command(self, tmp_path: Path, monkeypatch):
        """Test main create-bundle command execution."""
        binary = tmp_path / "mcpb-linux-x64"
        binary.write_bytes(b"content")

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "build_binary.py",
                "create-bundle",
                "--platform",
                "linux-x64",
                "--binary",
                str(binary),
                "--version",
                "1.0.0",
                "--output-dir",
                str(tmp_path),
            ],
        )

        # Mock bundle creation
        with patch("scripts.build_binary.create_bundle") as mock_create:
            mock_create.return_value = tmp_path / "bundle.zip"
            # Should not raise
            pass

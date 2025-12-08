"""Tests for mcpb manifest data models.

Tests cover:
- Platform enum validation
- BinaryMetadata model validation
- PlatformManifest model validation
- JSON serialization/deserialization
- Checksum computation
"""

import json
from pathlib import Path

import pytest

from code_indexer.mcpb.manifest import (
    Platform,
    BinaryMetadata,
    PlatformManifest,
    compute_sha256,
)


class TestPlatformEnum:
    """Test Platform enum values."""

    def test_platform_values(self):
        """Test platform enum has expected values."""
        assert Platform.DARWIN_X64.value == "darwin-x64"
        assert Platform.DARWIN_ARM64.value == "darwin-arm64"
        assert Platform.LINUX_X64.value == "linux-x64"
        assert Platform.WINDOWS_X64.value == "windows-x64"

    def test_platform_string_conversion(self):
        """Test platform can be created from string."""
        assert Platform("darwin-x64") == Platform.DARWIN_X64
        assert Platform("linux-x64") == Platform.LINUX_X64

    def test_platform_invalid_value(self):
        """Test invalid platform value raises ValueError."""
        with pytest.raises(ValueError):
            Platform("invalid-platform")


class TestBinaryMetadata:
    """Test BinaryMetadata model."""

    def test_valid_metadata(self):
        """Test creating valid binary metadata."""
        metadata = BinaryMetadata(
            binary="mcpb-darwin-x64",
            sha256="a" * 64,
            size=1024000,
        )
        assert metadata.binary == "mcpb-darwin-x64"
        assert metadata.sha256 == "a" * 64
        assert metadata.size == 1024000

    def test_metadata_json_serialization(self):
        """Test metadata serializes to JSON correctly."""
        metadata = BinaryMetadata(
            binary="mcpb-linux-x64",
            sha256="b" * 64,
            size=2048000,
        )
        json_data = metadata.model_dump()
        assert json_data == {
            "binary": "mcpb-linux-x64",
            "sha256": "b" * 64,
            "size": 2048000,
        }

    def test_metadata_from_json(self):
        """Test creating metadata from JSON data."""
        json_data = {
            "binary": "cidx-semantic-search.exe",
            "sha256": "c" * 64,
            "size": 3072000,
        }
        metadata = BinaryMetadata(**json_data)
        assert metadata.binary == "cidx-semantic-search.exe"
        assert metadata.sha256 == "c" * 64
        assert metadata.size == 3072000

    def test_metadata_invalid_sha256_length(self):
        """Test metadata validation rejects invalid SHA256."""
        with pytest.raises(ValueError):
            BinaryMetadata(
                binary="mcpb",
                sha256="tooshort",  # SHA256 must be 64 hex chars
                size=1024,
            )

    def test_metadata_negative_size(self):
        """Test metadata validation rejects negative size."""
        with pytest.raises(ValueError):
            BinaryMetadata(
                binary="mcpb",
                sha256="a" * 64,
                size=-1,
            )


class TestPlatformManifest:
    """Test PlatformManifest model."""

    def test_valid_manifest(self):
        """Test creating valid platform manifest."""
        platforms = {
            Platform.DARWIN_X64: BinaryMetadata(
                binary="mcpb-darwin-x64",
                sha256="a" * 64,
                size=1024000,
            ),
            Platform.LINUX_X64: BinaryMetadata(
                binary="mcpb-linux-x64",
                sha256="b" * 64,
                size=2048000,
            ),
        }

        manifest = PlatformManifest(
            name="mcpb",
            version="1.0.0",
            description="MCP Stdio Bridge for CIDX",
            mcp_version="2024-11-05",
            platforms=platforms,
            configuration={
                "command": ["mcpb"],
                "env": ["CIDX_SERVER_URL", "CIDX_BEARER_TOKEN"],
            },
        )

        assert manifest.name == "mcpb"
        assert manifest.version == "1.0.0"
        assert manifest.mcp_version == "2024-11-05"
        assert len(manifest.platforms) == 2
        assert Platform.DARWIN_X64 in manifest.platforms
        assert Platform.LINUX_X64 in manifest.platforms

    def test_manifest_default_mcp_version(self):
        """Test manifest uses default MCP version."""
        manifest = PlatformManifest(
            name="mcpb",
            version="1.0.0",
            description="Test",
            platforms={},
            configuration={},
        )
        assert manifest.mcp_version == "2024-11-05"

    def test_manifest_json_serialization(self):
        """Test manifest serializes to JSON correctly."""
        platforms = {
            Platform.DARWIN_X64: BinaryMetadata(
                binary="mcpb-darwin-x64",
                sha256="a" * 64,
                size=1024000,
            ),
        }

        manifest = PlatformManifest(
            name="mcpb",
            version="1.0.0",
            description="Test Bridge",
            platforms=platforms,
            configuration={"command": ["mcpb"]},
        )

        json_data = manifest.model_dump()
        assert json_data["name"] == "mcpb"
        assert json_data["version"] == "1.0.0"
        assert json_data["mcp_version"] == "2024-11-05"
        assert "darwin-x64" in json_data["platforms"]
        assert json_data["platforms"]["darwin-x64"]["binary"] == "mcpb-darwin-x64"

    def test_manifest_json_roundtrip(self):
        """Test manifest can be serialized and deserialized."""
        original = PlatformManifest(
            name="mcpb",
            version="2.0.0",
            description="Test",
            platforms={
                Platform.LINUX_X64: BinaryMetadata(
                    binary="mcpb-linux-x64",
                    sha256="b" * 64,
                    size=2048000,
                ),
            },
            configuration={"command": ["mcpb"], "env": ["VAR1"]},
        )

        # Serialize to JSON
        json_str = original.model_dump_json()
        json_data = json.loads(json_str)

        # Deserialize back
        restored = PlatformManifest(**json_data)

        assert restored.name == original.name
        assert restored.version == original.version
        assert restored.description == original.description
        assert len(restored.platforms) == len(original.platforms)
        assert Platform.LINUX_X64 in restored.platforms
        assert restored.platforms[Platform.LINUX_X64].binary == "mcpb-linux-x64"

    def test_manifest_empty_platforms(self):
        """Test manifest can have empty platforms dict."""
        manifest = PlatformManifest(
            name="mcpb",
            version="1.0.0",
            description="Test",
            platforms={},
            configuration={},
        )
        assert len(manifest.platforms) == 0


class TestChecksumComputation:
    """Test checksum computation utilities."""

    def test_compute_sha256_file(self, tmp_path: Path):
        """Test computing SHA256 of a file."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"Hello, World!")

        checksum = compute_sha256(test_file)
        # Known SHA256 of "Hello, World!"
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert checksum == expected

    def test_compute_sha256_empty_file(self, tmp_path: Path):
        """Test computing SHA256 of empty file."""
        test_file = tmp_path / "empty.bin"
        test_file.write_bytes(b"")

        checksum = compute_sha256(test_file)
        # Known SHA256 of empty string
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert checksum == expected

    def test_compute_sha256_large_file(self, tmp_path: Path):
        """Test computing SHA256 of large file (chunked reading)."""
        test_file = tmp_path / "large.bin"
        # Create 10MB file
        test_file.write_bytes(b"x" * (10 * 1024 * 1024))

        checksum = compute_sha256(test_file)
        # Just verify it returns 64 hex characters
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_compute_sha256_nonexistent_file(self, tmp_path: Path):
        """Test computing SHA256 of nonexistent file raises error."""
        test_file = tmp_path / "nonexistent.bin"

        with pytest.raises(FileNotFoundError):
            compute_sha256(test_file)

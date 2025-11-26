#!/usr/bin/env python3
"""Build automation script for MCP Bridge binaries.

This script provides commands for:
- Building platform-specific binaries with PyInstaller
- Verifying binary functionality
- Computing checksums
- Generating manifests
- Creating distribution bundles

Usage:
    python3 scripts/build_binary.py build [--output-dir DIR]
    python3 scripts/build_binary.py verify --binary PATH --version VERSION
    python3 scripts/build_binary.py create-bundle --platform PLATFORM --binary PATH --version VERSION
"""

import argparse
import os
import platform as platform_module
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from code_indexer.mcpb.manifest import (
    Platform,
    BinaryMetadata,
    PlatformManifest,
    compute_sha256,
)


def detect_platform() -> str:
    """Detect current platform identifier.

    Returns:
        Platform identifier string (e.g., "darwin-x64", "linux-x64")

    Raises:
        ValueError: If platform or architecture is not supported
    """
    system = platform_module.system()
    machine = platform_module.machine()

    # Map system names
    if system == "Darwin":
        os_name = "darwin"
    elif system == "Linux":
        os_name = "linux"
    elif system == "Windows":
        os_name = "windows"
    else:
        raise ValueError(f"Unsupported platform: {system}")

    # Map architecture names
    if machine in ("x86_64", "AMD64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise ValueError(f"Unsupported architecture: {machine}")

    platform_id = f"{os_name}-{arch}"

    # Validate against Platform enum
    try:
        Platform(platform_id)
    except ValueError:
        raise ValueError(f"Unsupported platform combination: {platform_id}")

    return platform_id


def verify_binary(binary_path: Path, expected_version: str) -> bool:
    """Verify binary executes and returns expected version.

    Args:
        binary_path: Path to binary file
        expected_version: Expected version string (without 'v' prefix)

    Returns:
        True if binary is valid and version matches
    """
    if not binary_path.exists():
        print(f"Binary not found: {binary_path}", file=sys.stderr)
        return False

    # Check if executable
    if not os.access(binary_path, os.X_OK):
        print(f"Binary not executable: {binary_path}", file=sys.stderr)
        return False

    try:
        # Run binary with --version flag
        result = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            print(f"Binary execution failed: {result.stderr}", file=sys.stderr)
            return False

        # Check version string
        output = result.stdout.strip()
        # Extract version from output (may include program name)
        # Examples: "mcpb 8.2.0", "mcpb-linux-x64 8.2.0", "v8.2.0", "8.2.0"
        parts = output.split()
        version = parts[-1].lstrip("v")  # Get last part, remove 'v' prefix if present

        if version != expected_version:
            print(
                f"Version mismatch: expected {expected_version}, got {version}",
                file=sys.stderr,
            )
            return False

        print(f"Binary verified: {binary_path} (version {version})")
        return True

    except subprocess.TimeoutExpired:
        print(f"Binary execution timed out: {binary_path}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Binary verification failed: {e}", file=sys.stderr)
        return False


def create_manifest(
    name: str,
    version: str,
    description: str,
    binaries: dict[str, Path],
    configuration: Optional[dict] = None,
) -> PlatformManifest:
    """Create platform manifest from binaries.

    Args:
        name: Package name
        version: Version string
        description: Package description
        binaries: Dict mapping platform IDs to binary paths
        configuration: Optional MCP configuration template

    Returns:
        PlatformManifest instance

    Raises:
        FileNotFoundError: If any binary does not exist
    """
    platforms = {}

    for platform_id, binary_path in binaries.items():
        if not binary_path.exists():
            raise FileNotFoundError(f"Binary not found: {binary_path}")

        # Compute metadata
        platform_enum = Platform(platform_id)
        metadata = BinaryMetadata(
            binary=binary_path.name,
            sha256=compute_sha256(binary_path),
            size=binary_path.stat().st_size,
        )
        platforms[platform_enum] = metadata

    if configuration is None:
        configuration = {
            "command": [name],
            "env": ["CIDX_SERVER_URL", "CIDX_BEARER_TOKEN"],
        }

    manifest = PlatformManifest(
        name=name,
        version=version,
        description=description,
        platforms=platforms,
        configuration=configuration,
    )

    return manifest


def create_bundle(
    platform_id: str,
    binary: Path,
    manifest: dict,
    output_dir: Path,
) -> Path:
    """Create MCPB bundle with binary and manifest.

    Args:
        platform_id: Platform identifier (e.g., "darwin-x64")
        binary: Path to binary file
        manifest: Manifest data as dict (unused - replaced with MCPB spec format)
        output_dir: Output directory for bundle

    Returns:
        Path to created MCPB bundle
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create bundle filename - MCPB extension instead of .zip
    bundle_name = f"mcpb-{platform_id}.mcpb"
    bundle_path = output_dir / bundle_name

    # Determine server/ subdirectory path for binary
    if platform_id.startswith("windows"):
        server_binary_name = f"server/mcpb-{platform_id}.exe"
        entry_point = (
            f"server/mcpb-{platform_id}"  # .exe added automatically by Windows
        )
        command = f"server/mcpb-{platform_id}.exe"
    else:
        server_binary_name = (
            f"server/mcpb-{platform_id}"  # No .mcpb extension inside bundle
        )
        entry_point = server_binary_name
        command = entry_point

    # Extract version from manifest or use default
    version = manifest.get("version", "8.2.0")

    # Create MCPB spec-compliant manifest
    import json

    mcpb_manifest = {
        "manifest_version": "0.3",
        "name": "cidx-mcpb",
        "version": version,
        "description": "MCP Stdio Bridge for CIDX - enables Claude Desktop to perform semantic code searches",
        "author": {
            "name": "Seba Battig",
            "url": "https://github.com/jsbattig/code-indexer",
        },
        "server": {
            "type": "binary",
            "entry_point": entry_point,
            "mcp_config": {
                "command": command,
                "args": [],
                "env": {"CIDX_SERVER_URL": "", "CIDX_TOKEN": ""},
            },
        },
        "compatibility": {
            "platforms": [platform_id.split("-")[0]]  # "darwin", "linux", or "win32"
        },
    }

    # Create ZIP with binary in server/ subdirectory and manifest
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add binary to server/ subdirectory with executable permissions
        info = zipfile.ZipInfo(server_binary_name)
        info.external_attr = (
            0o755 << 16 | 0x8000
        )  # Unix permissions + regular file flag

        with open(binary, "rb") as f:
            zf.writestr(info, f.read(), zipfile.ZIP_DEFLATED)

        # Add MCPB spec-compliant manifest
        manifest_json = json.dumps(mcpb_manifest, indent=2)
        zf.writestr("manifest.json", manifest_json)

    print(f"Created bundle: {bundle_path}")
    return bundle_path


def build_binary(output_dir: Path, platform_id: Optional[str] = None) -> Path:
    """Build binary using PyInstaller.

    Args:
        output_dir: Output directory for binary
        platform_id: Optional platform identifier (auto-detected if not provided)

    Returns:
        Path to built binary

    Raises:
        RuntimeError: If build fails
    """
    if platform_id is None:
        platform_id = detect_platform()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine binary name
    binary_name = f"mcpb-{platform_id}"
    if platform_id.startswith("windows"):
        binary_name += ".exe"
    # Don't add .mcpb here - only the bundle gets .mcpb extension

    # Find spec file
    spec_file = Path(__file__).parent.parent / "pyinstaller.spec"
    if not spec_file.exists():
        raise FileNotFoundError(f"PyInstaller spec file not found: {spec_file}")

    # Run PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(output_dir),
        str(spec_file),
    ]

    print(f"Building binary for {platform_id}...")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"PyInstaller build failed with code {result.returncode}")

    # Find built binary
    built_binary = output_dir / "mcpb"
    if platform_id.startswith("windows"):
        built_binary = output_dir / "mcpb.exe"

    if not built_binary.exists():
        raise RuntimeError(f"Built binary not found: {built_binary}")

    # Rename to platform-specific name
    final_binary = output_dir / binary_name
    built_binary.rename(final_binary)

    print(f"Built binary: {final_binary}")
    return final_binary


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build automation for MCP Bridge binaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Build command
    build_parser = subparsers.add_parser("build", help="Build binary with PyInstaller")
    build_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        help="Output directory (default: dist)",
    )
    build_parser.add_argument(
        "--platform",
        type=str,
        help="Platform identifier (auto-detected if not provided)",
    )

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify binary functionality")
    verify_parser.add_argument(
        "--binary",
        type=Path,
        required=True,
        help="Path to binary file",
    )
    verify_parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="Expected version string",
    )

    # Create-bundle command
    bundle_parser = subparsers.add_parser(
        "create-bundle", help="Create distribution bundle"
    )
    bundle_parser.add_argument(
        "--platform",
        type=str,
        required=True,
        help="Platform identifier (e.g., darwin-x64)",
    )
    bundle_parser.add_argument(
        "--binary",
        type=Path,
        required=True,
        help="Path to binary file",
    )
    bundle_parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="Version string",
    )
    bundle_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        help="Output directory (default: dist)",
    )

    args = parser.parse_args()

    if args.command == "build":
        try:
            binary = build_binary(args.output_dir, args.platform)
            print(f"Success: {binary}")
            sys.exit(0)
        except Exception as e:
            print(f"Build failed: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "verify":
        if verify_binary(args.binary, args.version):
            print("Verification passed")
            sys.exit(0)
        else:
            print("Verification failed", file=sys.stderr)
            sys.exit(1)

    elif args.command == "create-bundle":
        try:
            # Create simple manifest
            manifest = create_manifest(
                name="mcpb",
                version=args.version,
                description="MCP Stdio Bridge for CIDX",
                binaries={args.platform: args.binary},
            )

            bundle = create_bundle(
                platform_id=args.platform,
                binary=args.binary,
                manifest=manifest.model_dump(),
                output_dir=args.output_dir,
            )
            print(f"Success: {bundle}")
            sys.exit(0)
        except Exception as e:
            print(f"Bundle creation failed: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

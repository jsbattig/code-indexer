# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for MCP Bridge (mcpb).

This spec file builds a single-file executable for the MCP Stdio Bridge.
The binary includes all dependencies and can run without a Python installation.

Usage:
    pyinstaller --clean pyinstaller.spec

The output will be in dist/mcpb (or dist/mcpb.exe on Windows).
"""

import sys
from pathlib import Path

# Determine project root
spec_dir = Path(SPECPATH)
project_root = spec_dir
src_dir = project_root / "src"

# Add src to Python path for imports
sys.path.insert(0, str(src_dir))

a = Analysis(
    # Entry point: mcpb bridge main module
    [str(src_dir / "code_indexer" / "mcpb" / "bridge.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    # Hidden imports: modules not detected by static analysis
    hiddenimports=[
        # MCPB modules (required for relative imports)
        "code_indexer.mcpb",
        "code_indexer.mcpb.config",
        "code_indexer.mcpb.diagnostics",
        "code_indexer.mcpb.http_client",
        "code_indexer.mcpb.protocol",
        "code_indexer.mcpb.sse_parser",
        "code_indexer.mcpb.manifest",
        # HTTP/2 support for httpx
        "httpx",
        "h2",
        "h2.connection",
        "h2.config",
        "h2.events",
        "h2.exceptions",
        "hpack",
        "httpcore",
        "httpcore._backends",
        "httpcore._backends.sync",
        "httpcore._sync",
        # Pydantic for config validation
        "pydantic",
        "pydantic.fields",
        "pydantic.main",
        # JSON handling
        "json",
        # Async support
        "asyncio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude unnecessary modules to reduce binary size
    excludes=[
        "tkinter",
        "unittest",
        "test",
        "pytest",
        "setuptools",
        "pip",
        "wheel",
        # Exclude heavy data science libraries if present
        "numpy",
        "pandas",
        "scipy",
        "matplotlib",
        # Exclude testing frameworks
        "pytest",
        "hypothesis",
        "coverage",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mcpb",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Enable UPX compression for smaller binary
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console application (stdio bridge)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

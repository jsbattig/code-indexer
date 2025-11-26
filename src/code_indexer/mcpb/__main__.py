"""Entry point for MCPB bridge when run as a module or standalone binary.

This file serves as a clean entry point without relative imports, making it
compatible with PyInstaller bundling.
"""

import sys


def main():
    """Main entry point for the MCPB bridge."""
    # Import bridge.main after sys.path is set up
    from code_indexer.mcpb.bridge import main as bridge_main

    return bridge_main()


if __name__ == "__main__":
    sys.exit(main())

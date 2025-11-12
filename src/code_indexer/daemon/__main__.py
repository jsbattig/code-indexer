"""Entry point for CIDX daemon service.

Usage:
    python -m code_indexer.daemon <config_path>
    python -m code_indexer.daemon /path/to/project/.code-indexer/config.json

The daemon will bind to a Unix socket in the same directory as the config file.
"""

import argparse
import logging
import sys
from pathlib import Path

from .server import start_daemon

# Setup logging - Output to both console and file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Console output
    ],
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for daemon service."""
    parser = argparse.ArgumentParser(
        description="CIDX Daemon Service - In-memory index caching"
    )
    parser.add_argument(
        "config_path", type=Path, help="Path to .code-indexer/config.json"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate config path
    config_path = args.config_path

    # Add file handler for daemon logs
    daemon_log_file = config_path.parent / "daemon.log"
    file_handler = logging.FileHandler(daemon_log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logging.getLogger().addHandler(file_handler)
    logger.info(f"Daemon logging to {daemon_log_file}")
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    if not config_path.is_file():
        logger.error(f"Config path is not a file: {config_path}")
        print(f"ERROR: Config path is not a file: {config_path}", file=sys.stderr)
        sys.exit(1)

    # Start daemon
    logger.info(f"Starting daemon for {config_path}")
    start_daemon(config_path)


if __name__ == "__main__":
    main()

"""
Load environment variables from .env files for tests.
This ensures tests have access to API keys stored in .env files.
"""

import os
from pathlib import Path


def load_env_file(env_file: Path) -> None:
    """Load environment variables from a .env file without requiring python-dotenv."""
    if not env_file.exists():
        return

    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Handle export statements
            if line.startswith("export "):
                line = line[7:]  # Remove 'export '

            # Parse KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value


# Load .env files when this module is imported
project_root = Path(__file__).parent.parent

# Load .env.local if it exists
env_local = project_root / ".env.local"
if env_local.exists():
    load_env_file(env_local)

# Load .env if it exists
env_file = project_root / ".env"
if env_file.exists():
    load_env_file(env_file)

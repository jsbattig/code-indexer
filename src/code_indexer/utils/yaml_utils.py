"""YAML utilities for language mappings configuration."""

import yaml  # type: ignore
from pathlib import Path
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE_MAPPINGS = {
    # Programming languages
    "python": ["py", "pyw", "pyi"],
    "javascript": ["js", "jsx"],
    "typescript": ["ts", "tsx"],
    "java": ["java"],
    "csharp": ["cs"],
    "c": ["c", "h"],
    "cpp": ["cpp", "cc", "cxx", "c++"],
    "c++": ["cpp", "cc", "cxx", "c++"],  # Alias for cpp
    "go": ["go"],
    "rust": ["rs"],
    "php": ["php"],
    "ruby": ["rb"],
    "swift": ["swift"],
    "kotlin": ["kt", "kts"],
    "scala": ["scala"],
    "dart": ["dart"],
    # Web technologies
    "html": ["html", "htm"],
    "css": ["css"],
    "vue": ["vue"],
    # Markup and documentation
    "markdown": ["md", "markdown"],
    "xml": ["xml"],
    "latex": ["tex", "latex"],
    "rst": ["rst"],
    # Data and configuration
    "json": ["json"],
    "yaml": ["yaml", "yml"],
    "toml": ["toml"],
    "ini": ["ini"],
    "sql": ["sql"],
    # Shell and scripting
    "shell": ["sh", "bash"],
    "bash": ["sh", "bash"],
    "powershell": ["ps1", "psm1", "psd1"],
    "batch": ["bat", "cmd"],
    # Build and config files
    "dockerfile": ["dockerfile"],
    "makefile": ["makefile", "mk"],
    "cmake": ["cmake"],
    # Other formats
    "text": ["txt"],
    "log": ["log"],
    "csv": ["csv"],
}


def create_language_mappings_yaml(config_dir: Path, force: bool = False) -> bool:
    """
    Create language-mappings.yaml file with default mappings.

    Args:
        config_dir: The .code-indexer directory path
        force: Whether to overwrite existing file

    Returns:
        True if file was created, False if already exists and not forced
    """
    yaml_path = config_dir / "language-mappings.yaml"

    if yaml_path.exists() and not force:
        logger.debug(f"Language mappings file already exists: {yaml_path}")
        return False

    # Ensure directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    # Create YAML content with documentation
    yaml_content = """# Language Mappings Configuration
# Maps friendly language names to file extensions for CIDX query filtering
#
# Format:
#   language_name: [extension1, extension2, ...]
#
# Examples:
#   python: [py, pyw, pyi]
#   javascript: [js, jsx]
#
# You can add custom languages or modify existing mappings below.
# Changes take effect on next query execution.

"""

    # Write mappings
    with open(yaml_path, "w") as f:
        f.write(yaml_content)
        yaml.dump(
            DEFAULT_LANGUAGE_MAPPINGS,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    logger.info(f"Created language mappings file: {yaml_path}")
    return True


def load_language_mappings_yaml(yaml_path: Path) -> Dict[str, Set[str]]:
    """
    Load language mappings from YAML file.

    Args:
        yaml_path: Path to language-mappings.yaml

    Returns:
        Dictionary mapping language names to sets of extensions

    Raises:
        FileNotFoundError: If YAML file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    if not yaml_path.exists():
        raise FileNotFoundError(f"Language mappings file not found: {yaml_path}")

    try:
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        # Convert lists to sets for consistency
        mappings = {}
        for lang, extensions in data.items():
            if isinstance(extensions, list):
                mappings[lang] = set(extensions)
            elif isinstance(extensions, str):
                # Single extension as string
                mappings[lang] = {extensions}
            else:
                logger.warning(f"Invalid extension format for {lang}, skipping")

        return mappings

    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML file {yaml_path}: {e}")
        raise

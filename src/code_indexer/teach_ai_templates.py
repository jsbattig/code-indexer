"""Template loading functions for teach-ai command."""

import shutil
from pathlib import Path
from typing import List


def load_awareness_template(platform: str) -> str:
    """
    Load awareness template for any platform.

    Args:
        platform: Platform name (kept for API compatibility, not used)

    Returns:
        Template content as string

    Raises:
        FileNotFoundError: If template file not found
    """
    # Single awareness template for all platforms
    # (platform parameter kept for API compatibility)
    module_dir = Path(__file__).parent
    project_root = module_dir.parent.parent
    template_path = project_root / "prompts" / "ai_instructions" / "awareness" / "awareness.md"

    return template_path.read_text()


def install_skills(target_dir: str) -> List[str]:
    """
    Install skills template files to target directory with clean overwrite.

    Args:
        target_dir: Target directory path (e.g., ~/.claude/skills/cidx/)

    Returns:
        List of installed file paths (relative to target_dir)
    """
    target_path = Path(target_dir)

    # Clean overwrite: remove existing directory
    if target_path.exists():
        shutil.rmtree(target_path)

    # Create target directory
    target_path.mkdir(parents=True, exist_ok=True)

    # Get source skills template directory
    module_dir = Path(__file__).parent
    project_root = module_dir.parent.parent
    source_dir = project_root / "prompts" / "ai_instructions" / "skills" / "cidx"

    # Copy all files from source to target
    installed_files = []
    for source_file in source_dir.rglob("*"):
        if source_file.is_file():
            # Calculate relative path
            relative_path = source_file.relative_to(source_dir)
            target_file = target_path / relative_path

            # Create parent directory if needed
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(source_file, target_file)
            installed_files.append(str(relative_path))

    return installed_files

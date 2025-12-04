"""
Meta description lifecycle hooks for golden repositories.

Provides hooks that automatically create/delete .md files in cidx-meta
when golden repos are added/removed, eliminating the need for special-case
meta directory management code.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from code_indexer.server.services.claude_cli_manager import ClaudeCliManager

logger = logging.getLogger(__name__)

# README file detection order
README_NAMES = [
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "readme.md",
    "Readme.md",
]


def on_repo_added(
    repo_name: str,
    repo_url: str,
    clone_path: str,
    golden_repos_dir: str,
) -> None:
    """
    Hook called after a golden repository is successfully added.

    Creates a .md description file in cidx-meta and re-indexes cidx-meta.

    Args:
        repo_name: Name/alias of the repository
        repo_url: Repository URL
        clone_path: Path to cloned repository
        golden_repos_dir: Path to golden-repos directory

    Note:
        - Skips cidx-meta itself (no self-referential .md file)
        - Handles missing clone paths gracefully (logs warning, no crash)
        - Re-indexes cidx-meta after creating .md file
        - Falls back to README copy when Claude CLI unavailable or fails
    """
    # Skip cidx-meta itself
    if repo_name == "cidx-meta":
        logger.info("Skipping meta description generation for cidx-meta itself")
        return

    cidx_meta_path = Path(golden_repos_dir) / "cidx-meta"

    # Ensure cidx-meta directory exists
    if not cidx_meta_path.exists():
        logger.warning(
            f"cidx-meta directory does not exist at {cidx_meta_path}, cannot create .md file"
        )
        return

    # Check CLI availability
    cli_manager = ClaudeCliManager()
    if not cli_manager.check_cli_available():
        logger.info(f"Claude CLI unavailable, using README fallback for {repo_name}")
        _create_readme_fallback(Path(clone_path), repo_name, cidx_meta_path)
        return

    # Generate .md file
    try:
        md_content = _generate_repo_description(repo_name, repo_url, clone_path)
        md_file = cidx_meta_path / f"{repo_name}.md"
        md_file.write_text(md_content)
        logger.info(f"Created meta description file: {md_file}")

        # Re-index cidx-meta
        _reindex_cidx_meta(cidx_meta_path)

    except Exception as e:
        logger.error(
            f"Failed to create meta description for {repo_name}: {e}", exc_info=True
        )
        # Fall back to README copy
        logger.info(f"Falling back to README copy for {repo_name}")
        _create_readme_fallback(Path(clone_path), repo_name, cidx_meta_path)


def on_repo_removed(repo_name: str, golden_repos_dir: str) -> None:
    """
    Hook called after a golden repository is successfully removed.

    Deletes the .md description file from cidx-meta and re-indexes cidx-meta.

    Args:
        repo_name: Name/alias of the repository being removed
        golden_repos_dir: Path to golden-repos directory

    Note:
        - Handles nonexistent .md files gracefully (no crash)
        - Re-indexes cidx-meta only if file was actually deleted
    """
    cidx_meta_path = Path(golden_repos_dir) / "cidx-meta"
    md_file = cidx_meta_path / f"{repo_name}.md"

    # Delete .md file if it exists
    if md_file.exists():
        try:
            md_file.unlink()
            logger.info(f"Deleted meta description file: {md_file}")

            # Re-index cidx-meta
            _reindex_cidx_meta(cidx_meta_path)

        except Exception as e:
            logger.error(
                f"Failed to delete meta description for {repo_name}: {e}", exc_info=True
            )
            # Don't crash the golden repo remove operation - log and continue
    else:
        logger.debug(f"No meta description file to delete for {repo_name}")


def _find_readme(repo_path: Path) -> Optional[Path]:
    """
    Find README file in repository.

    Args:
        repo_path: Path to repository

    Returns:
        Path to README file if found, None otherwise

    Note:
        Checks README files in priority order defined by README_NAMES.
    """
    for readme_name in README_NAMES:
        readme_path = repo_path / readme_name
        if readme_path.exists():
            return readme_path
    return None


def _create_readme_fallback(
    repo_path: Path, alias: str, meta_dir: Path
) -> Optional[Path]:
    """
    Create README fallback file in meta directory.

    Args:
        repo_path: Path to repository
        alias: Repository alias/name
        meta_dir: Path to cidx-meta directory

    Returns:
        Path to created fallback file if README found, None otherwise

    Note:
        - Creates file named <alias>_README.md
        - Preserves original README content exactly
        - Triggers re-index of cidx-meta after creation
    """
    readme_path = _find_readme(repo_path)
    if readme_path is None:
        logger.warning(f"No README found in {repo_path} for fallback")
        return None

    # Create fallback file with <alias>_README.md naming
    fallback_path = meta_dir / f"{alias}_README.md"

    try:
        # Copy README content exactly
        content = readme_path.read_text(encoding="utf-8")
        fallback_path.write_text(content, encoding="utf-8")
        logger.info(f"Created README fallback: {fallback_path}")

        # Trigger re-index
        _reindex_cidx_meta(meta_dir)

        return fallback_path

    except Exception as e:
        logger.error(
            f"Failed to create README fallback for {alias}: {e}", exc_info=True
        )
        return None


def _generate_repo_description(repo_name: str, repo_url: str, clone_path: str) -> str:
    """
    Generate .md file content for a repository using RepoAnalyzer.

    Args:
        repo_name: Repository name/alias
        repo_url: Repository URL
        clone_path: Path to cloned repository

    Returns:
        Markdown content for .md file with rich metadata from Claude analysis
    """
    from datetime import datetime, timezone

    from .repo_analyzer import RepoAnalyzer

    now = datetime.now(timezone.utc).isoformat()

    # Use RepoAnalyzer for rich metadata extraction (uses Claude SDK if available)
    analyzer = RepoAnalyzer(clone_path)
    info = analyzer.extract_info()

    # Build YAML frontmatter with rich metadata
    tech_list = (
        "\n".join(f"  - {tech}" for tech in info.technologies)
        if info.technologies
        else "  []"
    )

    frontmatter = f"""---
name: {repo_name}
url: {repo_url}
technologies:
{tech_list}
purpose: {info.purpose}
last_analyzed: {now}
---
"""

    # Build body with summary and details
    body = f"""
# {repo_name}

{info.summary}

**Repository URL**: {repo_url}
"""

    # Add features section if available
    if info.features:
        body += "\n## Features\n\n"
        for feat in info.features[:10]:
            body += f"- {feat}\n"

    # Add use cases section if available
    if info.use_cases:
        body += "\n## Use Cases\n\n"
        for uc in info.use_cases[:5]:
            body += f"- {uc}\n"

    return frontmatter + body


def _reindex_cidx_meta(cidx_meta_path: Path) -> None:
    """
    Re-index cidx-meta after .md file changes.

    Args:
        cidx_meta_path: Path to cidx-meta directory

    Note:
        Runs 'cidx index' in cidx-meta directory.
        Logs errors but does not raise exceptions (non-critical operation).
    """
    try:
        result = subprocess.run(
            ["cidx", "index"],
            cwd=str(cidx_meta_path),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode != 0:
            logger.warning(
                f"cidx index failed for cidx-meta: {result.stderr or result.stdout}"
            )
        else:
            logger.info("Re-indexed cidx-meta successfully")

    except subprocess.TimeoutExpired:
        logger.error("cidx index timed out for cidx-meta")
    except Exception as e:
        logger.error(f"Failed to re-index cidx-meta: {e}", exc_info=True)

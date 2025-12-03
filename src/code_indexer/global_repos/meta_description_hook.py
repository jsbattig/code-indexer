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

logger = logging.getLogger(__name__)


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
        # Don't crash the golden repo add operation - log and continue


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


def _generate_repo_description(
    repo_name: str, repo_url: str, clone_path: str
) -> str:
    """
    Generate .md file content for a repository.

    Args:
        repo_name: Repository name/alias
        repo_url: Repository URL
        clone_path: Path to cloned repository

    Returns:
        Markdown content for .md file

    Note:
        Uses simple template-based generation. Future enhancement could
        integrate with RepoAnalyzer for richer metadata extraction.
    """
    from datetime import datetime, timezone

    # Basic template for now - can be enhanced later with RepoAnalyzer
    now = datetime.now(timezone.utc).isoformat()

    # Try to extract README content for description
    description = _extract_readme_summary(clone_path)

    frontmatter = f"""---
name: {repo_name}
url: {repo_url}
last_analyzed: {now}
---
"""

    body = f"""
# {repo_name}

{description}

**Repository URL**: {repo_url}
"""

    return frontmatter + body


def _extract_readme_summary(clone_path: str) -> str:
    """
    Extract summary from README file if available.

    Args:
        clone_path: Path to repository

    Returns:
        Summary text or generic description
    """
    clone_path_obj = Path(clone_path)

    # Look for README files
    readme_files = ["README.md", "README.txt", "README", "readme.md"]
    for readme_name in readme_files:
        readme_path = clone_path_obj / readme_name
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
                # Extract first non-empty paragraph (simple heuristic)
                lines = content.split("\n")
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#") and len(line) > 20:
                        return line[:500]  # First substantial line, max 500 chars
            except Exception as e:
                logger.debug(f"Failed to read README from {readme_path}: {e}")
                continue

    return f"Golden repository: {Path(clone_path).name}"


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

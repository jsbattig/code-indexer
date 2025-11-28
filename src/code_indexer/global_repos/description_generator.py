"""
Description Generator for creating repository description files.

Generates markdown files with YAML frontmatter containing repository
metadata and semantic descriptions optimized for search.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List


logger = logging.getLogger(__name__)


class DescriptionGenerator:
    """
    Generates repository description files in markdown format.

    Creates .md files with YAML frontmatter and markdown body for each
    repository, optimized for semantic search discovery.
    """

    def __init__(self, meta_dir: str):
        """
        Initialize the description generator.

        Args:
            meta_dir: Directory where description files will be stored
        """
        self.meta_dir = Path(meta_dir)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def create_description(
        self,
        repo_name: str,
        repo_url: str,
        description: str,
        technologies: List[str],
        purpose: str,
        features: List[str],
        use_cases: List[str],
    ) -> Path:
        """
        Create a description file for a repository.

        Args:
            repo_name: Name of the repository
            repo_url: URL of the repository
            description: Repository description
            technologies: List of technologies used
            purpose: Primary purpose of the repository
            features: List of key features
            use_cases: List of primary use cases

        Returns:
            Path to the created description file
        """
        desc_file = self.meta_dir / f"{repo_name}.md"
        now = datetime.now(timezone.utc).isoformat()

        # Build YAML frontmatter
        frontmatter = f"""---
name: {repo_name}
url: {repo_url}
technologies:
{self._format_yaml_list(technologies)}
purpose: {purpose}
last_analyzed: {now}
---
"""

        # Build markdown body
        body = f"""
# {repo_name}

{description}
"""

        if features:
            body += "\n## Key Features\n"
            for feature in features:
                body += f"- {feature}\n"

        if technologies:
            body += "\n## Technologies\n"
            for tech in technologies:
                body += f"- {tech}\n"

        if use_cases:
            body += "\n## Primary Use Cases\n"
            for use_case in use_cases:
                body += f"- {use_case}\n"

        # Write to file
        content = frontmatter + body
        desc_file.write_text(content)

        logger.info(f"Created description file: {desc_file}")
        return desc_file

    def _format_yaml_list(self, items: List[str]) -> str:
        """
        Format a list of items for YAML frontmatter.

        Args:
            items: List of string items

        Returns:
            Formatted YAML list string
        """
        if not items:
            return "  []"

        return "\n".join(f"  - {item}" for item in items)

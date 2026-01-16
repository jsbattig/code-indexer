"""
Delegation Function Loader Service.

Story #718: Function Discovery for claude.ai Users

Loads and parses delegation function definitions from markdown files with
YAML frontmatter in a configured golden repository.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DelegationFunction:
    """Represents a parsed delegation function definition."""

    name: str
    description: str
    allowed_groups: List[str]
    impersonation_user: Optional[str]
    required_repos: List[Dict[str, Any]]
    parameters: List[Dict[str, Any]]
    prompt_template: str


class DelegationFunctionLoader:
    """
    Loads and parses function definitions from repository.

    Function definitions are markdown files with YAML frontmatter containing
    metadata about allowed groups, parameters, and required repositories.
    """

    def __init__(self) -> None:
        """Initialize the DelegationFunctionLoader."""
        pass

    def load_functions(self, repo_path: Path) -> List[DelegationFunction]:
        """
        Load all function definitions from repository.

        Args:
            repo_path: Path to the function repository directory

        Returns:
            List of parsed DelegationFunction objects
        """
        functions: List[DelegationFunction] = []

        if not repo_path.exists() or not repo_path.is_dir():
            logger.warning(f"Function repository path does not exist: {repo_path}")
            return functions

        for file_path in repo_path.glob("*.md"):
            try:
                func = self.parse_function_file(file_path)
                functions.append(func)
            except ValueError as e:
                logger.warning(f"Skipping invalid function file {file_path}: {e}")
            except Exception as e:
                logger.warning(f"Error parsing function file {file_path}: {e}")

        return functions

    def parse_function_file(self, file_path: Path) -> DelegationFunction:
        """
        Parse single function definition file.

        Args:
            file_path: Path to the markdown file with YAML frontmatter

        Returns:
            Parsed DelegationFunction object

        Raises:
            ValueError: If the file is invalid or missing required fields
        """
        content = file_path.read_text()

        # Parse YAML frontmatter
        frontmatter, body = self._parse_frontmatter(content)

        if frontmatter is None:
            raise ValueError("No valid YAML frontmatter found")

        # Validate required fields
        if "name" not in frontmatter:
            raise ValueError("Missing required field: name")

        if "allowed_groups" not in frontmatter:
            raise ValueError("Missing required field: allowed_groups")

        allowed_groups = frontmatter.get("allowed_groups", [])
        if not allowed_groups:
            raise ValueError("allowed_groups cannot be empty")

        return DelegationFunction(
            name=frontmatter["name"],
            description=frontmatter.get("description", ""),
            allowed_groups=allowed_groups,
            impersonation_user=frontmatter.get("impersonation_user"),
            required_repos=frontmatter.get("required_repos", []),
            parameters=frontmatter.get("parameters", []),
            prompt_template=body,
        )

    def _parse_frontmatter(
        self, content: str
    ) -> tuple[Optional[Dict[str, Any]], str]:
        """
        Parse YAML frontmatter from markdown content.

        Args:
            content: Full markdown file content

        Returns:
            Tuple of (frontmatter dict or None, body content)
        """
        if not content.startswith("---"):
            return None, content

        # Find the closing ---
        end_index = content.find("---", 3)
        if end_index == -1:
            return None, content

        frontmatter_str = content[3:end_index].strip()
        body = content[end_index + 3:].strip()

        try:
            frontmatter = yaml.safe_load(frontmatter_str)
            if not isinstance(frontmatter, dict):
                return None, content
            return frontmatter, body
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse YAML frontmatter: {e}")
            return None, content

    def filter_by_groups(
        self, functions: List[DelegationFunction], user_groups: Set[str]
    ) -> List[DelegationFunction]:
        """
        Filter functions accessible to user's groups.

        Args:
            functions: List of DelegationFunction objects
            user_groups: Set of group names the user belongs to

        Returns:
            Filtered list of functions where allowed_groups intersects with user_groups
        """
        if not user_groups:
            return []

        return [
            func
            for func in functions
            if set(func.allowed_groups) & user_groups
        ]

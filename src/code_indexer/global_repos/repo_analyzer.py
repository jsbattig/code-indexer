"""
Repository Analyzer for extracting information from repositories.

Analyzes repository contents (README, package files, directory structure)
to extract metadata for generating semantic descriptions.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


logger = logging.getLogger(__name__)


@dataclass
class RepoInfo:
    """
    Repository information extracted by analyzer.

    Attributes:
        summary: High-level description of the repository
        technologies: List of technologies/languages detected
        features: List of key features
        use_cases: List of primary use cases
        purpose: Primary purpose of the repository
    """

    summary: str
    technologies: List[str]
    features: List[str]
    use_cases: List[str]
    purpose: str


class RepoAnalyzer:
    """
    Analyzes repository contents to extract information.

    Examines README files, package manifests, and directory structure
    to infer technologies, features, and purpose.
    """

    def __init__(self, repo_path: str):
        """
        Initialize the repository analyzer.

        Args:
            repo_path: Path to the repository to analyze
        """
        self.repo_path = Path(repo_path)

    def extract_info(self) -> RepoInfo:
        """
        Extract information from the repository.

        Returns:
            RepoInfo object containing extracted metadata
        """
        summary = self._extract_summary()
        technologies = self._detect_technologies()
        features = self._extract_features()
        use_cases = self._extract_use_cases()
        purpose = self._infer_purpose()

        return RepoInfo(
            summary=summary,
            technologies=technologies,
            features=features,
            use_cases=use_cases,
            purpose=purpose,
        )

    def _extract_summary(self) -> str:
        """
        Extract summary from README or infer from structure.

        Returns:
            Repository summary string
        """
        readme = self._find_readme()
        if readme:
            content = readme.read_text()

            # Extract first meaningful paragraph after title
            lines = content.split("\n")
            summary_lines = []

            skip_title = False
            for line in lines:
                line = line.strip()

                # Skip title line
                if line.startswith("#"):
                    skip_title = True
                    continue

                # Collect first paragraph
                if skip_title and line:
                    summary_lines.append(line)
                    if len(" ".join(summary_lines)) > 50:
                        break

            if summary_lines:
                return " ".join(summary_lines)

        # Fallback: use repo name
        return f"A {self.repo_path.name} repository"

    def _detect_technologies(self) -> List[str]:
        """
        Detect technologies from package files and directory structure.

        Returns:
            List of detected technologies
        """
        technologies = []

        # Check for Python
        if (
            (self.repo_path / "setup.py").exists()
            or (self.repo_path / "pyproject.toml").exists()
            or (self.repo_path / "requirements.txt").exists()
            or self._has_python_files()
        ):
            technologies.append("Python")

        # Check for JavaScript/Node.js
        if (self.repo_path / "package.json").exists():
            technologies.append("JavaScript")
            technologies.append("Node.js")

        # Check for Rust
        if (self.repo_path / "Cargo.toml").exists():
            technologies.append("Rust")

        # Check for Go
        if (self.repo_path / "go.mod").exists():
            technologies.append("Go")

        # Check for Java
        if (self.repo_path / "pom.xml").exists() or (
            self.repo_path / "build.gradle"
        ).exists():
            technologies.append("Java")

        # Extract from README Technologies section
        readme_techs = self._extract_technologies_from_readme()
        technologies.extend(readme_techs)

        # Remove duplicates while preserving order
        seen = set()
        unique_techs = []
        for tech in technologies:
            if tech not in seen:
                seen.add(tech)
                unique_techs.append(tech)

        return unique_techs

    def _extract_features(self) -> List[str]:
        """
        Extract features from README.

        Returns:
            List of features
        """
        features = []
        readme = self._find_readme()

        if readme:
            content = readme.read_text()

            # Look for Features section
            features_section = self._extract_section(content, "Features")
            if features_section:
                # Extract bullet points
                for line in features_section.split("\n"):
                    line = line.strip()
                    if line.startswith("-") or line.startswith("*"):
                        feature = line.lstrip("-*").strip()
                        if feature:
                            features.append(feature)

        return features

    def _extract_use_cases(self) -> List[str]:
        """
        Extract use cases from README.

        Returns:
            List of use cases
        """
        use_cases = []
        readme = self._find_readme()

        if readme:
            content = readme.read_text()

            # Look for Use Cases section
            use_cases_section = self._extract_section(content, "Use Cases")
            if use_cases_section:
                # Extract bullet points
                for line in use_cases_section.split("\n"):
                    line = line.strip()
                    if line.startswith("-") or line.startswith("*"):
                        use_case = line.lstrip("-*").strip()
                        if use_case:
                            use_cases.append(use_case)

        return use_cases

    def _infer_purpose(self) -> str:
        """
        Infer repository purpose from name and content.

        Returns:
            Inferred purpose string
        """
        repo_name = self.repo_path.name

        # Common purpose keywords
        if "api" in repo_name.lower():
            return "api"
        if "service" in repo_name.lower():
            return "service"
        if "lib" in repo_name.lower() or "library" in repo_name.lower():
            return "library"
        if "cli" in repo_name.lower():
            return "cli-tool"
        if "web" in repo_name.lower():
            return "web-application"
        if "auth" in repo_name.lower():
            return "authentication"

        # Default
        return "general-purpose"

    def _find_readme(self) -> Optional[Path]:
        """
        Find README file in repository.

        Returns:
            Path to README or None if not found
        """
        for name in ["README.md", "README.rst", "README.txt", "README"]:
            readme = self.repo_path / name
            if readme.exists():
                return readme
        return None

    def _has_python_files(self) -> bool:
        """
        Check if repository contains Python files.

        Returns:
            True if Python files found
        """
        # Check for __init__.py
        for path in self.repo_path.rglob("__init__.py"):
            return True

        # Check for .py files
        for path in self.repo_path.rglob("*.py"):
            return True

        return False

    def _extract_technologies_from_readme(self) -> List[str]:
        """
        Extract technologies from README Technologies section.

        Returns:
            List of technologies found in README
        """
        technologies = []
        readme = self._find_readme()

        if readme:
            content = readme.read_text()

            # Look for Technologies section
            tech_section = self._extract_section(content, "Technologies")
            if tech_section:
                # Extract bullet points
                for line in tech_section.split("\n"):
                    line = line.strip()
                    if line.startswith("-") or line.startswith("*"):
                        tech = line.lstrip("-*").strip()
                        if tech:
                            technologies.append(tech)

        return technologies

    def _extract_section(self, content: str, section_name: str) -> Optional[str]:
        """
        Extract a section from markdown content.

        Args:
            content: Markdown content
            section_name: Name of section to extract

        Returns:
            Section content or None if not found
        """
        lines = content.split("\n")
        in_section = False
        section_lines = []

        for line in lines:
            # Check for section header
            if re.match(f"^##+ {section_name}", line, re.IGNORECASE):
                in_section = True
                continue

            # Stop at next section
            if in_section and line.startswith("##"):
                break

            # Collect section content
            if in_section:
                section_lines.append(line)

        if section_lines:
            return "\n".join(section_lines)

        return None

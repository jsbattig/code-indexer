"""
Repository Analyzer for extracting information from repositories.

Analyzes repository contents (README, package files, directory structure)
to extract metadata for generating semantic descriptions.

Supports Claude CLI integration for enhanced AI-powered analysis when
CIDX_USE_CLAUDE_FOR_META environment variable is set to 'true' (default).
Requires ANTHROPIC_API_KEY environment variable and 'claude' CLI in PATH.
"""

import json
import logging
import os
import re
import shlex
import subprocess
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

        Uses Claude CLI for AI-powered analysis if available and enabled,
        otherwise falls back to static regex-based analysis.

        Returns:
            RepoInfo object containing extracted metadata
        """
        # Check if Claude is enabled (default: true)
        use_claude = (
            os.environ.get("CIDX_USE_CLAUDE_FOR_META", "true").lower() == "true"
        )

        if use_claude:
            claude_result = self._extract_info_with_claude()
            if claude_result is not None:
                return claude_result
            logger.info(
                "Claude analysis failed or unavailable, "
                "falling back to static analysis for %s",
                self.repo_path,
            )

        return self._extract_info_static()

    def _extract_info_with_claude(self) -> Optional[RepoInfo]:
        """
        Extract repository information using Claude CLI with tool support.

        Uses Claude Code CLI which can read files, explore directories,
        and provide much richer analysis than SDK-only approaches.

        Returns:
            RepoInfo if Claude succeeds and returns valid JSON,
            None otherwise (fallback to static analysis)
        """
        try:
            # Check if Claude CLI is available
            which_result = subprocess.run(
                ["which", "claude"], capture_output=True, text=True, timeout=5
            )
            if which_result.returncode != 0:
                logger.debug("Claude CLI not found in PATH")
                return None

            # Build the analysis prompt
            prompt = """Analyze this repository. Examine the README, source files, and package files.
Output ONLY a JSON object (no markdown, no explanation) with these exact fields:
{
  "summary": "2-3 sentence description of what this repository does",
  "technologies": ["list", "of", "all", "technologies", "and", "tools", "detected"],
  "features": ["key feature 1", "key feature 2", ...],
  "use_cases": ["primary use case 1", "use case 2", ...],
  "purpose": "one of: api, service, library, cli-tool, web-application, data-structure, utility, framework, general-purpose"
}"""

            # Use script to provide pseudo-TTY (required for Claude CLI in non-interactive environments)
            # The command: script -q -c 'timeout 90 claude -p "..." --print --dangerously-skip-permissions' /dev/null
            claude_cmd = f"timeout 90 claude -p {shlex.quote(prompt)} --print --dangerously-skip-permissions"
            full_cmd = ["script", "-q", "-c", claude_cmd, "/dev/null"]

            result = subprocess.run(
                full_cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ},  # Inherit environment including ANTHROPIC_API_KEY
            )

            if result.returncode != 0:
                logger.debug("Claude CLI returned non-zero: %d", result.returncode)
                return None

            # Clean output (remove ANSI escape codes and carriage returns)
            output = result.stdout
            output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)  # Remove ANSI escapes
            output = output.replace("\r\n", "\n").replace(
                "\r", ""
            )  # Normalize line endings
            output = output.strip()

            # Extract JSON from response (may be wrapped in markdown code blocks)
            if "```json" in output:
                match = re.search(r"```json\s*(.*?)\s*```", output, re.DOTALL)
                if match:
                    output = match.group(1)
            elif "```" in output:
                match = re.search(r"```\s*(.*?)\s*```", output, re.DOTALL)
                if match:
                    output = match.group(1)

            # Find JSON object in output
            json_match = re.search(
                r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", output, re.DOTALL
            )
            if json_match:
                output = json_match.group(0)

            # Parse JSON response
            data = json.loads(output)

            # Validate required fields
            required_fields = ["summary", "technologies", "purpose"]
            for field in required_fields:
                if field not in data:
                    logger.debug("Claude response missing required field: %s", field)
                    return None

            logger.info(
                "Successfully analyzed repository with Claude CLI: %s",
                self.repo_path.name,
            )

            return RepoInfo(
                summary=data["summary"],
                technologies=data.get("technologies", []),
                features=data.get("features", []),
                use_cases=data.get("use_cases", []),
                purpose=data.get("purpose", "general-purpose"),
            )

        except FileNotFoundError:
            logger.debug("script command not found")
            return None
        except subprocess.TimeoutExpired:
            logger.debug("Claude CLI timed out after 120 seconds")
            return None
        except json.JSONDecodeError as e:
            logger.debug("Failed to parse Claude CLI JSON response: %s", e)
            return None
        except Exception as e:
            logger.debug("Unexpected error during Claude CLI execution: %s", e)
            return None

    def _extract_info_static(self) -> RepoInfo:
        """
        Extract information using static regex-based analysis.

        Fallback method when Claude CLI is unavailable or disabled.

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

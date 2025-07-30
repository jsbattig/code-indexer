"""
Claude prompt setter service for injecting CIDX instructions into CLAUDE.md files.

This service manages the injection of semantic search instructions into CLAUDE.md files
to improve Claude Code integration with the code-indexer tool.
"""

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

from .cidx_instruction_builder import CidxInstructionBuilder

logger = logging.getLogger(__name__)


class ClaudePromptSetter:
    """Service for setting CIDX prompts in CLAUDE.md files."""

    def __init__(self, codebase_dir: Optional[Path] = None):
        """Initialize the prompt setter.

        Args:
            codebase_dir: Base directory for generating prompts (default: current dir)
        """
        self.codebase_dir = codebase_dir or Path.cwd()
        self.instruction_builder = CidxInstructionBuilder(self.codebase_dir)

        # Section markers for detecting existing CIDX content
        self.section_start_markers = [
            "CIDX SEMANTIC CODE SEARCH INTEGRATION",
            "SEMANTIC SEARCH INTEGRATION",
            "🎯 SEMANTIC SEARCH TOOL",
            "CIDX SEMANTIC SEARCH",
        ]

    def set_user_prompt(self) -> bool:
        """Set CIDX prompt in user's global CLAUDE.md file.

        Returns:
            True if successful, False otherwise
        """
        try:
            user_claude_file = self._find_user_claude_file()

            if user_claude_file is None:
                # Create new user CLAUDE.md file
                user_claude_file = Path.home() / ".claude" / "CLAUDE.md"
                user_claude_file.parent.mkdir(parents=True, exist_ok=True)

                prompt_content = self._generate_cidx_prompt()
                new_content = self._insert_cidx_section("", prompt_content)

                user_claude_file.write_text(new_content, encoding="utf-8")
                logger.info(
                    f"Created new user CLAUDE.md with CIDX prompt: {user_claude_file}"
                )
                return True

            # Update existing file
            existing_content = user_claude_file.read_text(encoding="utf-8")
            prompt_content = self._generate_cidx_prompt()

            start, end = self._detect_cidx_section(existing_content)
            if start is not None and end is not None:
                # Replace existing section
                new_content = self._replace_cidx_section(
                    existing_content, prompt_content
                )
                logger.info("Replaced existing CIDX section in user CLAUDE.md")
            else:
                # Insert new section
                new_content = self._insert_cidx_section(
                    existing_content, prompt_content
                )
                logger.info("Added new CIDX section to user CLAUDE.md")

            # Normalize line endings and write
            new_content = self._normalize_line_endings(new_content)
            user_claude_file.write_text(new_content, encoding="utf-8")

            return True

        except Exception as e:
            logger.error(f"Failed to set user prompt: {e}")
            return False

    def set_project_prompt(self, start_dir: Optional[Path] = None) -> bool:
        """Set CIDX prompt in project CLAUDE.md file.

        Args:
            start_dir: Directory to start searching from (default: current dir)

        Returns:
            True if successful, False if no CLAUDE.md found
        """
        try:
            start_dir = start_dir or Path.cwd()
            project_claude_file = self._find_project_claude_file(start_dir)

            if project_claude_file is None:
                logger.warning("No project CLAUDE.md file found")
                return False

            existing_content = project_claude_file.read_text(encoding="utf-8")
            prompt_content = self._generate_cidx_prompt()

            start, end = self._detect_cidx_section(existing_content)
            if start is not None and end is not None:
                # Replace existing section
                new_content = self._replace_cidx_section(
                    existing_content, prompt_content
                )
                logger.info(f"Replaced existing CIDX section in: {project_claude_file}")
            else:
                # Insert new section
                new_content = self._insert_cidx_section(
                    existing_content, prompt_content
                )
                logger.info(f"Added new CIDX section to: {project_claude_file}")

            # Normalize line endings and write
            new_content = self._normalize_line_endings(new_content)
            project_claude_file.write_text(new_content, encoding="utf-8")

            return True

        except Exception as e:
            logger.error(f"Failed to set project prompt: {e}")
            return False

    def _find_user_claude_file(self) -> Optional[Path]:
        """Find user's global CLAUDE.md file.

        Returns:
            Path to user CLAUDE.md or None if not found
        """
        user_claude_path = Path.home() / ".claude" / "CLAUDE.md"
        return user_claude_path if user_claude_path.exists() else None

    def _find_project_claude_file(self, start_dir: Path) -> Optional[Path]:
        """Find project CLAUDE.md by walking up directory tree.

        Args:
            start_dir: Directory to start searching from

        Returns:
            Path to project CLAUDE.md or None if not found
        """
        current_dir = start_dir.resolve()

        while current_dir != current_dir.parent:  # Stop at filesystem root
            claude_file = current_dir / "CLAUDE.md"
            if claude_file.exists():
                return claude_file
            current_dir = current_dir.parent

        return None

    def _detect_cidx_section(self, content: str) -> Tuple[Optional[int], Optional[int]]:
        """Detect existing CIDX section in content.

        Args:
            content: File content to search

        Returns:
            Tuple of (start_pos, end_pos) or (None, None) if not found
        """
        # Look for any of our section markers
        for marker in self.section_start_markers:
            pattern = rf"^.*{re.escape(marker)}.*$"
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

            if match:
                start_pos = match.start()

                # Find the end of this section by looking for:
                # 1. Next section starting with "- " at beginning of line
                # 2. Next heading starting with "#"
                # 3. End of file

                remaining_content = content[match.end() :]

                # Look for next section or heading
                next_section_pattern = r"\n(?=^- [A-Z]|^# |^## |^### )"
                next_match = re.search(
                    next_section_pattern, remaining_content, re.MULTILINE
                )

                if next_match:
                    end_pos = match.end() + next_match.start()
                else:
                    end_pos = len(content)

                return start_pos, end_pos

        return None, None

    def _insert_cidx_section(self, existing_content: str, cidx_prompt: str) -> str:
        """Insert CIDX section into content.

        Args:
            existing_content: Existing file content
            cidx_prompt: CIDX prompt to insert

        Returns:
            Updated content with CIDX section
        """
        section_header = "\n- CIDX SEMANTIC CODE SEARCH INTEGRATION\n\n"
        section_content = section_header + cidx_prompt + "\n"

        if not existing_content.strip():
            # Empty file
            return section_content

        # Insert at the end, with proper spacing
        if existing_content.endswith("\n"):
            return existing_content + section_content
        else:
            return existing_content + "\n" + section_content

    def _replace_cidx_section(self, content: str, cidx_prompt: str) -> str:
        """Replace existing CIDX section with new content.

        Args:
            content: File content with existing CIDX section
            cidx_prompt: New CIDX prompt

        Returns:
            Updated content with replaced CIDX section
        """
        start_pos, end_pos = self._detect_cidx_section(content)

        if start_pos is None or end_pos is None:
            # No existing section found, insert at end
            return self._insert_cidx_section(content, cidx_prompt)

        # Replace the section
        before = content[:start_pos]
        after = content[end_pos:]

        section_header = "- CIDX SEMANTIC CODE SEARCH INTEGRATION\n\n"
        new_section = section_header + cidx_prompt + "\n"

        return before + new_section + after

    def _normalize_line_endings(self, content: str) -> str:
        """Normalize line endings to LF (Unix style).

        Args:
            content: Content with potentially mixed line endings

        Returns:
            Content with normalized LF line endings
        """
        # Replace CRLF with LF, then CR with LF
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")

        # Ensure file ends with exactly one newline
        normalized = normalized.rstrip("\n") + "\n"

        return normalized

    def _generate_cidx_prompt(self) -> str:
        """Generate CIDX prompt content using instruction builder.

        Returns:
            Formatted CIDX instruction prompt
        """
        return self.instruction_builder.build_instructions(
            instruction_level="balanced",
            include_help_output=True,
            include_examples=True,
            include_advanced_patterns=False,
        )

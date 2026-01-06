"""Unit tests for teach-ai template loading functionality."""

import pytest
from pathlib import Path


class TestAwarenessTemplateLoader:
    """Test awareness template loading."""

    @pytest.mark.skip(
        reason="Requires prompts/ directory in installed package - packaging test, not unit test"
    )
    def test_load_awareness_template(self):
        """
        Test: Load awareness template for any platform
        Given any platform name
        When load_awareness_template() is called
        Then unified awareness.md content is returned
        And content contains essential CIDX documentation markers
        """
        from code_indexer.teach_ai_templates import load_awareness_template

        # Act - test with different platform names (all should return same content)
        claude_content = load_awareness_template("claude")
        codex_content = load_awareness_template("codex")

        # Assert - same content for all platforms (single template)
        assert claude_content == codex_content

        # Assert - content has required markers
        assert claude_content is not None
        assert len(claude_content) > 0
        assert "SEMANTIC SEARCH" in claude_content
        assert "CIDX FIRST" in claude_content
        assert "Read ~/.claude/skills/cidx/SKILL.md" in claude_content


class TestSkillsInstaller:
    """Test skills installation functionality."""

    @pytest.mark.skip(
        reason="Requires prompts/ directory in installed package - packaging test, not unit test"
    )
    def test_install_skills_creates_directory(self, tmp_path):
        """
        Test: Skills installation creates ~/.claude/skills/cidx/ directory
        Given ~/.claude/skills/cidx/ does not exist
        When install_skills() is called with target_dir
        Then directory is created
        And SKILL.md is created
        And reference/scip-intelligence.md is created
        """
        from code_indexer.teach_ai_templates import install_skills

        # Arrange
        skills_dir = tmp_path / ".claude" / "skills" / "cidx"

        # Act
        installed_files = install_skills(str(skills_dir))

        # Assert
        assert skills_dir.exists()
        assert (skills_dir / "SKILL.md").exists()
        assert (skills_dir / "reference" / "scip-intelligence.md").exists()

        # Count expected files from source template directory
        # Get source template directory
        code_indexer_root = Path(__file__).parent.parent.parent
        template_dir = (
            code_indexer_root / "prompts" / "ai_instructions" / "skills" / "cidx"
        )

        # Count all files in template directory (recursively)
        expected_count = sum(1 for _ in template_dir.rglob("*") if _.is_file())

        # Verify installed file count matches template count
        assert (
            len(installed_files) == expected_count
        ), f"Expected {expected_count} files, got {len(installed_files)}"

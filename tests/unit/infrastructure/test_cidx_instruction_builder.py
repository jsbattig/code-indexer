"""Tests for the unified CIDX instruction builder."""

import pytest

from pathlib import Path
from src.code_indexer.services.cidx_instruction_builder import (
    CidxInstructionBuilder,
    create_cidx_instructions,
)


class TestCidxInstructionBuilder:
    """Test the unified CIDX instruction builder."""

    def test_builder_initialization(self, local_tmp_path):
        """Test that the builder initializes correctly."""
        builder = CidxInstructionBuilder(local_tmp_path)
        assert builder.codebase_dir == local_tmp_path

    def test_builder_default_path(self):
        """Test that the builder uses current directory as default."""
        builder = CidxInstructionBuilder()
        assert builder.codebase_dir == Path.cwd()

    def test_minimal_instructions(self, local_tmp_path):
        """Test minimal instruction level."""
        builder = CidxInstructionBuilder(local_tmp_path)
        instructions = builder.build_instructions(
            instruction_level="minimal",
            include_help_output=False,
            include_examples=True,
            include_advanced_patterns=False,
        )

        # Should include simplified core intro
        assert "ABSOLUTE REQUIREMENT" in instructions
        assert "cidx query" in instructions

        # Should NOT include help output or strategic usage
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" not in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" not in instructions

    def test_balanced_instructions(self, local_tmp_path):
        """Test balanced instruction level (default)."""
        builder = CidxInstructionBuilder(local_tmp_path)
        instructions = builder.build_instructions()

        # Should include simplified core intro only
        assert "ABSOLUTE REQUIREMENT" in instructions
        assert "Mandatory CIDX-First Workflow" in instructions
        assert "cidx query" in instructions

        # Should NOT include verbose sections
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" not in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" not in instructions
        assert "💡 PRACTICAL EXAMPLES" not in instructions

    def test_comprehensive_instructions(self, local_tmp_path):
        """Test comprehensive instruction level."""
        builder = CidxInstructionBuilder(local_tmp_path)
        instructions = builder.build_instructions(
            instruction_level="comprehensive",
            include_help_output=True,
            include_examples=True,
            include_advanced_patterns=True,
        )

        # Now comprehensive is same as other levels - just simplified content
        assert "ABSOLUTE REQUIREMENT" in instructions
        assert "Mandatory CIDX-First Workflow" in instructions
        assert "cidx query" in instructions

        # No longer includes verbose sections
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" not in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" not in instructions

    def test_examples_always_use_quiet_flag(self, local_tmp_path):
        """Test that examples in simplified version use --quiet flag appropriately."""
        builder = CidxInstructionBuilder(local_tmp_path)
        instructions = builder.build_instructions()

        # The simplified version has specific examples in the bash code block
        assert 'cidx query "authentication function" --quiet' in instructions
        assert (
            'cidx query "error handling patterns" --language python --quiet'
            in instructions
        )
        assert (
            'cidx query "database connection" --path */services/* --quiet'
            in instructions
        )

        # Some examples don't use --quiet for demonstration purposes
        assert 'cidx query "authentication system login" --limit 10' in instructions

    def test_instructions_focus_on_cidx_usage(self, local_tmp_path):
        """Test that instructions focus on cidx tool usage, not citation requirements."""
        builder = CidxInstructionBuilder(local_tmp_path)
        instructions = builder.build_instructions()

        # Should focus on cidx usage
        assert "cidx query" in instructions
        assert "ABSOLUTE REQUIREMENT" in instructions
        assert "Mandatory CIDX-First Workflow" in instructions

    def test_convenience_function_minimal(self, local_tmp_path):
        """Test convenience function with minimal approach."""
        instructions = create_cidx_instructions(local_tmp_path, "minimal")

        assert "ABSOLUTE REQUIREMENT" in instructions
        assert "Mandatory CIDX-First Workflow" in instructions

        # Should NOT include verbose sections
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" not in instructions

    def test_convenience_function_balanced(self, local_tmp_path):
        """Test convenience function with balanced approach."""
        instructions = create_cidx_instructions(local_tmp_path, "balanced")

        assert "ABSOLUTE REQUIREMENT" in instructions
        assert "Mandatory CIDX-First Workflow" in instructions

        # Should NOT include verbose sections
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" not in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" not in instructions

    def test_convenience_function_comprehensive(self, local_tmp_path):
        """Test convenience function with comprehensive approach."""
        instructions = create_cidx_instructions(local_tmp_path, "comprehensive")

        assert "ABSOLUTE REQUIREMENT" in instructions
        assert "Mandatory CIDX-First Workflow" in instructions

        # All modes now return same simplified content
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" not in instructions

    def test_convenience_function_with_advanced(self, local_tmp_path):
        """Test convenience function with advanced patterns enabled."""
        instructions = create_cidx_instructions(
            local_tmp_path, "balanced", include_advanced=True
        )

        # All modes now return same simplified content
        assert "ABSOLUTE REQUIREMENT" in instructions
        assert "🔬 ADVANCED SEARCH STRATEGIES" not in instructions

    def test_help_output_includes_language_list(self, local_tmp_path):
        """Test that simplified version doesn't include help output."""
        builder = CidxInstructionBuilder(local_tmp_path)
        instructions = builder.build_instructions(include_help_output=True)

        # Simplified version doesn't include language list
        assert "🎯 SUPPORTED LANGUAGES" not in instructions
        assert "ABSOLUTE REQUIREMENT" in instructions

    def test_strategic_usage_includes_scoring_guidance(self, local_tmp_path):
        """Test that simplified version doesn't include scoring guidance."""
        builder = CidxInstructionBuilder(local_tmp_path)
        instructions = builder.build_instructions(
            instruction_level="balanced", include_help_output=True
        )

        # Simplified version doesn't include scoring guidance
        assert "📊 UNDERSTANDING SCORES" not in instructions
        assert "ABSOLUTE REQUIREMENT" in instructions

    def test_all_sections_properly_joined(self, local_tmp_path):
        """Test that all sections are properly joined with double newlines."""
        builder = CidxInstructionBuilder(local_tmp_path)
        instructions = builder.build_instructions(
            instruction_level="comprehensive", include_advanced_patterns=True
        )

        # Should have proper section separation
        sections = instructions.split("\n\n")
        assert len(sections) >= 5  # Should have multiple distinct sections

        # Each section should be non-empty
        for section in sections:
            assert section.strip(), "Each section should have content"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

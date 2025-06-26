"""Tests for the unified CIDX instruction builder."""

import pytest
from pathlib import Path
from src.code_indexer.services.cidx_instruction_builder import (
    CidxInstructionBuilder,
    create_cidx_instructions,
)


class TestCidxInstructionBuilder:
    """Test the unified CIDX instruction builder."""

    def test_builder_initialization(self, tmp_path):
        """Test that the builder initializes correctly."""
        builder = CidxInstructionBuilder(tmp_path)
        assert builder.codebase_dir == tmp_path

    def test_builder_default_path(self):
        """Test that the builder uses current directory as default."""
        builder = CidxInstructionBuilder()
        assert builder.codebase_dir == Path.cwd()

    def test_minimal_instructions(self, tmp_path):
        """Test minimal instruction level."""
        builder = CidxInstructionBuilder(tmp_path)
        instructions = builder.build_instructions(
            instruction_level="minimal",
            include_help_output=False,
            include_examples=True,
            include_advanced_patterns=False,
        )

        # Should include core intro (evidence requirements now handled by Claude integration)
        assert "🎯 SEMANTIC SEARCH TOOL" in instructions
        assert "cidx query" in instructions

        # Should NOT include help output or strategic usage
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" not in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" not in instructions

    def test_balanced_instructions(self, tmp_path):
        """Test balanced instruction level (default)."""
        builder = CidxInstructionBuilder(tmp_path)
        instructions = builder.build_instructions()

        # Should include core components
        assert "🎯 SEMANTIC SEARCH TOOL" in instructions
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" in instructions
        assert "💡 PRACTICAL EXAMPLES" in instructions

        # Should NOT include advanced patterns
        assert "🔬 ADVANCED SEARCH STRATEGIES" not in instructions

    def test_comprehensive_instructions(self, tmp_path):
        """Test comprehensive instruction level."""
        builder = CidxInstructionBuilder(tmp_path)
        instructions = builder.build_instructions(
            instruction_level="comprehensive",
            include_help_output=True,
            include_examples=True,
            include_advanced_patterns=True,
        )

        # Should include all components
        assert "🎯 SEMANTIC SEARCH TOOL" in instructions
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" in instructions
        assert "💡 PRACTICAL EXAMPLES" in instructions
        assert "🔬 ADVANCED SEARCH STRATEGIES" in instructions

    def test_examples_always_use_quiet_flag(self, tmp_path):
        """Test that all examples consistently use --quiet flag."""
        builder = CidxInstructionBuilder(tmp_path)
        instructions = builder.build_instructions(include_examples=True)

        # Extract example commands and verify they use --quiet
        example_commands = []
        lines = instructions.split("\n")
        for line in lines:
            if "cidx query" in line and "`" in line:
                # Extract the command from backticks
                start = line.find("`")
                end = line.rfind("`")
                if start != -1 and end != -1 and start != end:
                    command = line[start + 1 : end]
                    # Only check commands that have arguments (actual examples)
                    if "cidx query" in command and len(command.split()) > 2:
                        example_commands.append(command)

        # Verify all commands use --quiet
        assert len(example_commands) > 0, "Should have found example commands"
        for cmd in example_commands:
            assert "--quiet" in cmd, f"Command should use --quiet: {cmd}"

    def test_instructions_focus_on_cidx_usage(self, tmp_path):
        """Test that instructions focus on cidx tool usage, not citation requirements."""
        builder = CidxInstructionBuilder(tmp_path)
        instructions = builder.build_instructions()

        # Should focus on cidx usage
        assert "cidx query" in instructions
        assert "SEMANTIC SEARCH TOOL" in instructions
        # Citation format is now handled by Claude integration, not here

    def test_convenience_function_minimal(self, tmp_path):
        """Test convenience function with minimal approach."""
        instructions = create_cidx_instructions(tmp_path, "minimal")

        assert "🎯 SEMANTIC SEARCH TOOL" in instructions
        assert "💡 PRACTICAL EXAMPLES" in instructions

        # Should NOT include help output for minimal
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" not in instructions

    def test_convenience_function_balanced(self, tmp_path):
        """Test convenience function with balanced approach."""
        instructions = create_cidx_instructions(tmp_path, "balanced")

        assert "🎯 SEMANTIC SEARCH TOOL" in instructions
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" in instructions
        assert "💡 PRACTICAL EXAMPLES" in instructions

        # Should NOT include advanced patterns for balanced
        assert "🔬 ADVANCED SEARCH STRATEGIES" not in instructions

    def test_convenience_function_comprehensive(self, tmp_path):
        """Test convenience function with comprehensive approach."""
        instructions = create_cidx_instructions(tmp_path, "comprehensive")

        assert "🎯 SEMANTIC SEARCH TOOL" in instructions
        assert "📖 COMPLETE CIDX QUERY COMMAND REFERENCE" in instructions
        assert "🚀 STRATEGIC USAGE PATTERNS" in instructions
        assert "💡 PRACTICAL EXAMPLES" in instructions
        assert "🔬 ADVANCED SEARCH STRATEGIES" in instructions

    def test_convenience_function_with_advanced(self, tmp_path):
        """Test convenience function with advanced patterns enabled."""
        instructions = create_cidx_instructions(
            tmp_path, "balanced", include_advanced=True
        )

        # Should include advanced patterns even for balanced when explicitly enabled
        assert "🔬 ADVANCED SEARCH STRATEGIES" in instructions

    def test_help_output_includes_language_list(self, tmp_path):
        """Test that help output includes the supported languages list."""
        builder = CidxInstructionBuilder(tmp_path)
        instructions = builder.build_instructions(include_help_output=True)

        # Should include language categories and specific languages
        assert "🎯 SUPPORTED LANGUAGES" in instructions
        assert "Backend" in instructions
        assert "Frontend" in instructions
        assert "python" in instructions
        assert "javascript" in instructions
        assert "typescript" in instructions

    def test_strategic_usage_includes_scoring_guidance(self, tmp_path):
        """Test that strategic usage includes score interpretation."""
        builder = CidxInstructionBuilder(tmp_path)
        instructions = builder.build_instructions(
            instruction_level="balanced", include_help_output=True
        )

        # Should include scoring guidance
        assert "📊 UNDERSTANDING SCORES" in instructions
        assert "Score 0.9-1.0" in instructions
        assert "Score 0.7-0.8" in instructions

    def test_all_sections_properly_joined(self, tmp_path):
        """Test that all sections are properly joined with double newlines."""
        builder = CidxInstructionBuilder(tmp_path)
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

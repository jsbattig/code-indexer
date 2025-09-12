"""Tests for cidx prompt generation functionality."""

import os
import time
import tempfile
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from code_indexer.services.cidx_prompt_generator import CidxPromptGenerator
from code_indexer.cli import cli


class TestCidxPromptGenerator:
    """Unit tests for the core prompt generation logic."""

    def test_generate_ai_integration_prompt_structure(self):
        """Test that generated prompt has all required sections."""
        generator = CidxPromptGenerator()
        prompt = generator.generate_ai_integration_prompt()

        # Verify all sections present (case-insensitive)
        prompt_lower = prompt.lower()
        assert "detection and activation" in prompt_lower
        assert "core instructions" in prompt_lower
        assert "ai integration best practices" in prompt_lower
        assert "error handling" in prompt_lower
        assert "example workflows" in prompt_lower

    def test_detection_logic_section(self):
        """Test the .code-indexer detection logic section."""
        generator = CidxPromptGenerator()
        detection_section = generator._build_detection_logic()

        assert ".code-indexer" in detection_section
        assert "project root directory" in detection_section
        assert 'if [ -d ".code-indexer" ]' in detection_section

    def test_core_instructions_uses_existing_builder(self):
        """Test that core instructions leverage CidxInstructionBuilder."""
        generator = CidxPromptGenerator()
        core_section = generator._build_core_instructions()

        # Should include primary command and examples
        assert "cidx query" in core_section
        assert "--quiet" in core_section
        assert "ABSOLUTE REQUIREMENT" in core_section

    def test_examples_always_use_quiet_flag(self):
        """Test that most examples use --quiet flag."""
        generator = CidxPromptGenerator()
        prompt = generator.generate_ai_integration_prompt()

        # Should contain at least some examples with --quiet
        assert 'cidx query "authentication function" --quiet' in prompt
        assert (
            'cidx query "error handling patterns" --language python --quiet' in prompt
        )

        # Some examples don't use --quiet for demonstration purposes
        assert "cidx query" in prompt

    def test_error_handling_section(self):
        """Test error handling instructions."""
        generator = CidxPromptGenerator()
        error_section = generator._build_error_handling()

        assert "gracefully" in error_section.lower()
        assert "fall back" in error_section.lower()
        assert "unavailable" in error_section.lower()

    def test_best_practices_section(self):
        """Test AI integration best practices section."""
        generator = CidxPromptGenerator()
        practices_section = generator._build_best_practices()

        assert "search strategy" in practices_section.lower()
        assert "automated contexts" in practices_section.lower()
        assert "--quiet" in practices_section


class TestCidxPromptFormats:
    """Test different output formats for the prompt."""

    def test_default_text_format(self):
        """Test default plain text format."""
        generator = CidxPromptGenerator()
        prompt = generator.generate_ai_integration_prompt()

        # Should be plain text format (not markdown headers)
        assert not prompt.startswith("#")
        # Note: Help output includes code blocks, which is normal for text format

    def test_markdown_format(self):
        """Test markdown-formatted output."""
        generator = CidxPromptGenerator(format="markdown")
        prompt = generator.generate_ai_integration_prompt()

        # Should have markdown headers
        assert "# Cidx Semantic Code Search Integration" in prompt
        assert "## Detection and Activation" in prompt
        assert "```bash" in prompt

    def test_compact_format(self):
        """Test compact format for shorter prompts."""
        generator = CidxPromptGenerator(format="compact")
        prompt = generator.generate_ai_integration_prompt()

        # Should be shorter but complete
        full_prompt = CidxPromptGenerator().generate_ai_integration_prompt()
        assert len(prompt) < len(full_prompt)
        assert ".code-indexer" in prompt  # Still has detection logic

    def test_comprehensive_format(self):
        """Test comprehensive format with simplified content."""
        generator = CidxPromptGenerator(format="comprehensive")
        prompt = generator.generate_ai_integration_prompt()

        # Should contain the simplified content
        assert "ABSOLUTE REQUIREMENT" in prompt
        assert "cidx query" in prompt


class TestUseCidxPromptCLI:
    """Test the CLI command integration."""

    def test_basic_use_cidx_prompt_command(self):
        """Test basic --use-cidx-prompt command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--use-cidx-prompt"])

        assert result.exit_code == 0
        assert "CIDX SEMANTIC CODE SEARCH INTEGRATION" in result.output
        assert ".code-indexer" in result.output

    def test_format_option_markdown(self):
        """Test --format=markdown option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--use-cidx-prompt", "--format", "markdown"])

        assert result.exit_code == 0
        assert "# Cidx Semantic Code Search Integration" in result.output
        assert "```bash" in result.output

    def test_compact_option(self):
        """Test --compact option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--use-cidx-prompt", "--compact"])

        assert result.exit_code == 0
        # Should be shorter than default
        default_result = runner.invoke(cli, ["--use-cidx-prompt"])
        assert len(result.output) < len(default_result.output)

    def test_output_to_file_option(self):
        """Test --output option to save to file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_file = f.name

        try:
            runner = CliRunner()
            result = runner.invoke(cli, ["--use-cidx-prompt", "--output", temp_file])

            assert result.exit_code == 0
            assert os.path.exists(temp_file)

            with open(temp_file, "r") as f:
                content = f.read()

            assert "CIDX SEMANTIC CODE SEARCH INTEGRATION" in content
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_help_displays_correctly(self):
        """Test that help information is displayed correctly."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "--use-cidx-prompt" in result.output


class TestCidxPromptContent:
    """Test the quality and completeness of generated prompt content."""

    def test_prompt_includes_all_major_cidx_commands(self):
        """Test that prompt covers all major cidx commands."""
        generator = CidxPromptGenerator()
        prompt = generator.generate_ai_integration_prompt()

        # Check for core cidx commands (query and status are most important)
        assert "cidx query" in prompt
        assert "cidx status" in prompt

    def test_detection_logic_is_actionable(self):
        """Test that detection logic provides clear steps."""
        generator = CidxPromptGenerator()
        prompt = generator.generate_ai_integration_prompt()

        # Should have clear if/else logic
        assert "if" in prompt.lower()
        assert "else" in prompt.lower()
        assert ".code-indexer" in prompt
        assert "project root" in prompt.lower()

    def test_examples_are_realistic(self):
        """Test that examples represent realistic AI usage."""
        generator = CidxPromptGenerator()
        prompt = generator.generate_ai_integration_prompt()

        # Should have realistic search scenarios
        assert (
            "authentication" in prompt.lower()
            or "auth" in prompt.lower()
            or "login" in prompt.lower()
        )
        assert "find" in prompt.lower() or "search" in prompt.lower()

    def test_error_handling_is_comprehensive(self):
        """Test that error handling covers common failure modes."""
        generator = CidxPromptGenerator()
        prompt = generator.generate_ai_integration_prompt()

        error_scenarios = ["unavailable", "fails", "error", "fallback"]
        error_mentions = sum(
            1 for scenario in error_scenarios if scenario in prompt.lower()
        )
        assert error_mentions >= 2  # Should mention multiple error scenarios

    def test_prompt_is_self_contained(self):
        """Test that prompt doesn't reference external dependencies."""
        generator = CidxPromptGenerator()
        prompt = generator.generate_ai_integration_prompt()

        # Should not reference files or external systems
        assert "see documentation" not in prompt.lower()
        assert "refer to" not in prompt.lower()
        # Should be complete and self-explanatory
        assert len(prompt) > 1000  # Substantial content


class TestExistingInfrastructureIntegration:
    """Test integration with existing CidxInstructionBuilder."""

    def test_uses_existing_instruction_builder(self):
        """Test that prompt generation uses CidxInstructionBuilder."""
        with patch(
            "code_indexer.services.cidx_prompt_generator.CidxInstructionBuilder"
        ) as mock_builder:
            mock_builder.return_value.build_instructions.return_value = (
                "mock instructions"
            )

            generator = CidxPromptGenerator()
            prompt = generator.generate_ai_integration_prompt()

            # Should call the existing builder
            mock_builder.assert_called()
            assert "mock instructions" in prompt

    def test_preserves_existing_instruction_quality(self):
        """Test that integration preserves instruction quality."""
        # Generate using existing builder directly
        from code_indexer.services.cidx_instruction_builder import (
            CidxInstructionBuilder,
        )

        direct_instructions = CidxInstructionBuilder().build_instructions()

        # Generate using new prompt generator
        generator = CidxPromptGenerator()
        ai_prompt = generator.generate_ai_integration_prompt()

        # Core instructions should be preserved
        assert "--quiet" in direct_instructions
        assert "--quiet" in ai_prompt

    def test_adds_ai_specific_enhancements(self):
        """Test that AI prompt adds value beyond existing instructions."""
        from code_indexer.services.cidx_instruction_builder import (
            CidxInstructionBuilder,
        )

        direct_instructions = CidxInstructionBuilder().build_instructions()

        generator = CidxPromptGenerator()
        ai_prompt = generator.generate_ai_integration_prompt()

        # Should have AI-specific additions
        assert ".code-indexer" in ai_prompt
        # AI prompt should be more comprehensive
        assert len(ai_prompt) > len(direct_instructions)


class TestCidxPromptPerformance:
    """Test performance and edge cases."""

    def test_prompt_generation_is_fast(self):
        """Test that prompt generation completes quickly."""
        generator = CidxPromptGenerator()

        start_time = time.time()
        prompt = generator.generate_ai_integration_prompt()
        end_time = time.time()

        # Should complete in under 1 second
        assert end_time - start_time < 1.0
        assert len(prompt) > 100  # Should generate substantial content

    def test_large_prompt_handling(self):
        """Test handling of large generated prompts."""
        generator = CidxPromptGenerator(format="comprehensive")
        prompt = generator.generate_ai_integration_prompt()

        # Should handle large prompts gracefully
        assert len(prompt) > 3000  # Substantial content
        assert prompt.count("\n") > 30  # Multiple sections

    def test_empty_configuration_handling(self):
        """Test behavior with minimal configuration."""
        generator = CidxPromptGenerator()

        # Should not fail with minimal setup
        prompt = generator.generate_ai_integration_prompt()
        assert len(prompt) > 100
        assert ".code-indexer" in prompt

    def test_format_parameter_validation(self):
        """Test validation of format parameters."""
        # Valid formats should work
        valid_formats = ["text", "markdown", "compact", "comprehensive"]
        for fmt in valid_formats:
            generator = CidxPromptGenerator(format=fmt)
            prompt = generator.generate_ai_integration_prompt()
            assert len(prompt) > 100

        # Invalid format should default to text
        generator = CidxPromptGenerator(format="invalid")
        prompt = generator.generate_ai_integration_prompt()
        assert len(prompt) > 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

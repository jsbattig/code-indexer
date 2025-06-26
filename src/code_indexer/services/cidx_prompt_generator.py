"""
Cidx Prompt Generator

Generates comprehensive prompts for other AI systems to use cidx for semantic indexing.
Includes detection logic for .code-indexer folders and usage instructions.
"""

from code_indexer.services.cidx_instruction_builder import CidxInstructionBuilder


class CidxPromptGenerator:
    """Generates comprehensive cidx usage prompts for other AI systems."""

    def __init__(self, format: str = "text"):
        """Initialize the prompt generator.

        Args:
            format: Output format ("text", "markdown", "compact", "comprehensive")
        """
        self.format = (
            format
            if format in ["text", "markdown", "compact", "comprehensive"]
            else "text"
        )
        self.instruction_builder = CidxInstructionBuilder()

    def generate_ai_integration_prompt(self) -> str:
        """Generate complete prompt for AI integration."""
        sections = []

        # Add appropriate header based on format
        if self.format == "markdown":
            sections.append("# Cidx Semantic Code Search Integration")
        else:
            sections.append("CIDX SEMANTIC CODE SEARCH INTEGRATION")
            sections.append("=" * 50)

        sections.extend(
            [
                self._build_detection_logic(),
                self._build_activation_conditions(),
                self._build_core_instructions(),
                self._build_examples_section(),
                self._build_error_handling(),
                self._build_best_practices(),
            ]
        )

        return "\n\n".join(sections)

    def _build_detection_logic(self) -> str:
        """Instructions for detecting .code-indexer folders."""
        if self.format == "markdown":
            return """## Detection and Activation

Before using cidx commands, check if the project supports semantic search:

1. Look for a `.code-indexer` folder in the project root directory
2. If found, cidx semantic search is available for this project
3. Use cidx commands to search and analyze the codebase
4. If not found, fall back to standard file operations

### Detection Example

```bash
# Check for cidx availability
if [ -d ".code-indexer" ]; then
    echo "Cidx semantic search available"
    cidx status --quiet
else
    echo "Standard file operations only"
fi
```"""
        else:
            return """DETECTION AND ACTIVATION
----------------------

Before using cidx commands, check if the project supports semantic search:

1. Look for a .code-indexer folder in the project root directory
2. If found, cidx semantic search is available for this project
3. Use cidx commands to search and analyze the codebase
4. If not found, fall back to standard file operations

Detection Example:

if [ -d ".code-indexer" ]; then
    echo "Cidx semantic search available"
    cidx status --quiet
else
    echo "Standard file operations only"
fi"""

    def _build_activation_conditions(self) -> str:
        """When and how to activate cidx usage."""
        if self.format == "compact":
            return """WHEN TO USE CIDX:
- .code-indexer folder exists in project root
- Use cidx query --quiet for semantic searches
- Use cidx status --quiet to check system health
- Always include --quiet flag in automated contexts"""

        if self.format == "markdown":
            return """## Activation Conditions

Use cidx when:
- `.code-indexer` folder exists in the project root
- You need to search for code patterns or functionality
- You need to understand code relationships
- You want semantic search instead of text-based search

**Always use the `--quiet` flag when integrating with AI systems.**"""
        else:
            return """ACTIVATION CONDITIONS
-------------------

Use cidx when:
- .code-indexer folder exists in the project root
- You need to search for code patterns or functionality
- You need to understand code relationships
- You want semantic search instead of text-based search

IMPORTANT: Always use the --quiet flag when integrating with AI systems."""

    def _build_core_instructions(self) -> str:
        """Core cidx usage instructions using existing infrastructure."""
        if self.format == "compact":
            # Use minimal instructions for compact format
            core_instructions = self.instruction_builder.build_instructions(
                instruction_level="minimal"
            )
        elif self.format == "comprehensive":
            # Use comprehensive instructions with advanced patterns
            core_instructions = self.instruction_builder.build_instructions(
                instruction_level="comprehensive", include_advanced_patterns=True
            )
        else:
            # Use balanced instructions for default and markdown
            core_instructions = self.instruction_builder.build_instructions(
                instruction_level="balanced"
            )

        # Instructions already have --quiet flags from the builder

        if self.format == "markdown":
            return f"""## Core Instructions

{core_instructions}"""
        else:
            return f"""CORE INSTRUCTIONS
----------------

{core_instructions}"""

    def _build_examples_section(self) -> str:
        """Build realistic examples section."""
        examples = [
            (
                "Find authentication code",
                'cidx query --quiet "authentication login auth user"',
            ),
            (
                "Search for database functions",
                'cidx query --quiet "database sql query connection"',
            ),
            (
                "Find error handling",
                'cidx query --quiet "error exception handling try catch"',
            ),
            (
                "Look for API endpoints",
                'cidx query --quiet "api endpoint route handler"',
            ),
            (
                "Find configuration code",
                'cidx query --quiet "config configuration settings"',
            ),
        ]

        if self.format == "compact":
            example_text = "EXAMPLES:\n"
            for desc, cmd in examples[:3]:  # Only show first 3 in compact mode
                example_text += f"- {desc}: {cmd}\n"
            return example_text.rstrip()

        if self.format == "markdown":
            section = """## Example Workflows

### Common Search Scenarios

"""
            for desc, cmd in examples:
                section += f"**{desc}:**\n```bash\n{cmd}\n```\n\n"
            return section.rstrip()
        else:
            section = """EXAMPLE WORKFLOWS
----------------

Common Search Scenarios:

"""
            for desc, cmd in examples:
                section += f"* {desc}:\n  {cmd}\n\n"
            return section.rstrip()

    def _build_error_handling(self) -> str:
        """Build error handling instructions."""
        if self.format == "compact":
            return """ERROR HANDLING:
- If cidx fails, fall back to standard file operations
- Check cidx status --quiet if commands fail
- .code-indexer folder required for cidx functionality"""

        if self.format == "markdown":
            return """## Error Handling

### When Cidx is Unavailable
- Fall back to standard file operations (grep, find, etc.)
- Do not attempt cidx commands if `.code-indexer` folder is missing
- Handle command failures gracefully

### Troubleshooting
- Use `cidx status --quiet` to check system health
- Verify `.code-indexer` folder exists in project root
- If cidx commands fail, provide helpful error messages to users"""
        else:
            return """ERROR HANDLING
-------------

When Cidx is Unavailable:
- Fall back to standard file operations (grep, find, etc.)
- Do not attempt cidx commands if .code-indexer folder is missing
- Handle command failures gracefully

Troubleshooting:
- Use cidx status --quiet to check system health
- Verify .code-indexer folder exists in project root
- If cidx commands fail, provide helpful error messages to users"""

    def _build_best_practices(self) -> str:
        """Build AI integration best practices section."""
        if self.format == "compact":
            return """BEST PRACTICES:
- Always use --quiet flag
- Check .code-indexer folder first
- Prefer semantic search over text search when available
- Graceful fallback to standard tools"""

        practices = [
            "Always use --quiet flag in automated contexts",
            "Check for .code-indexer folder before using cidx",
            "Prefer semantic search over text-based search when available",
            "Provide graceful fallback to standard file operations",
            "Use cidx status --quiet to verify system health",
            "Handle errors gracefully and inform users appropriately",
        ]

        if self.format == "markdown":
            section = """## AI Integration Best Practices

### Search Strategy
"""
            for practice in practices:
                section += f"- {practice}\n"

            section += """\n### Integration Pattern
```
1. Check if .code-indexer exists
2. If yes: Use cidx query --quiet for searches
3. If no: Use standard grep/find commands
4. Always handle errors gracefully
```"""
            return section
        else:
            section = """AI INTEGRATION BEST PRACTICES
----------------------------

Search Strategy:
"""
            for practice in practices:
                section += f"- {practice}\n"

            section += """\nIntegration Pattern:
1. Check if .code-indexer exists
2. If yes: Use cidx query --quiet for searches
3. If no: Use standard grep/find commands
4. Always handle errors gracefully"""
            return section

    def _ensure_quiet_flag(self, content: str) -> str:
        """Ensure all cidx commands in content use --quiet flag."""
        import re

        # Find cidx commands that don't have --quiet
        pattern = r"(cidx\s+[^-\n]*?)(\s|$)"

        def add_quiet(match):
            command = match.group(1)
            if "--quiet" not in command:
                return command + " --quiet" + match.group(2)
            return match.group(0)

        return re.sub(pattern, add_quiet, content)


def create_cidx_ai_prompt(format: str = "text") -> str:
    """Convenience function to create cidx AI integration prompt.

    Args:
        format: Output format ("text", "markdown", "compact", "comprehensive")

    Returns:
        Complete prompt for AI integration
    """
    generator = CidxPromptGenerator(format=format)
    return generator.generate_ai_integration_prompt()

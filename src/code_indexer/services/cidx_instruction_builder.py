"""
Unified CIDX instruction builder for consistent Claude prompting.

This module provides a centralized way to build CIDX tool instructions
for Claude, ensuring consistency between claude-first and RAG-first approaches.
"""

from typing import Optional
from pathlib import Path


class CidxInstructionBuilder:
    """Builds consistent CIDX tool instructions for Claude prompts."""

    def __init__(self, codebase_dir: Optional[Path] = None):
        """Initialize the instruction builder.

        Args:
            codebase_dir: Path to codebase for citation formatting
        """
        self.codebase_dir = codebase_dir or Path.cwd()

    def build_instructions(
        self,
        instruction_level: str = "balanced",
        include_help_output: bool = True,
        include_examples: bool = True,
        include_advanced_patterns: bool = False,
    ) -> str:
        """Build CIDX instructions for Claude.

        Args:
            instruction_level: Level of detail - "minimal", "balanced", or "comprehensive"
            include_help_output: Whether to include full --help output
            include_examples: Whether to include usage examples
            include_advanced_patterns: Whether to include advanced search patterns

        Returns:
            Formatted instruction string
        """
        sections = []

        # Core CIDX introduction
        sections.append(self._build_core_introduction())

        if include_help_output:
            sections.append(self._build_help_output())

        # Strategic usage based on level
        if instruction_level in ["balanced", "comprehensive"]:
            sections.append(self._build_strategic_usage())

        if include_examples:
            sections.append(self._build_examples())

        if include_advanced_patterns:
            sections.append(self._build_advanced_patterns())

        # Evidence requirements removed - now handled by Claude integration service

        return "\n\n".join(sections)

    def _build_core_introduction(self) -> str:
        """Build the core CIDX introduction."""
        return """🎯 SEMANTIC SEARCH TOOL - YOUR PRIMARY CODE DISCOVERY METHOD

CRITICAL: You have access to a powerful semantic search tool `cidx query` that can find relevant code across the entire codebase. Use it liberally - it's much more effective than guessing or making assumptions.

**🧠 WHAT MAKES CIDX QUERY UNIQUE**:
- **Semantic Understanding**: Finds code related to concepts even when exact words don't match
- **Context Awareness**: Understands relationships between functions, classes, and modules  
- **Relevance Scoring**: Returns results ranked by semantic similarity (0.0-1.0 scale)
- **Git-Aware**: Searches within current project/branch context
- **Cross-Language**: Finds similar patterns across different programming languages

**WHEN TO USE CIDX QUERY**:
✅ "Where is X implemented?" → Search immediately with `cidx query "X implementation" --quiet`
✅ "How does Y work?" → Search for Y-related code first: `cidx query "Y functionality" --quiet`  
✅ "What files contain Z?" → Use semantic search: `cidx query "Z" --quiet`
✅ "Show me examples of..." → Search for examples: `cidx query "examples of..." --quiet`
✅ "Is there any code that..." → Search to verify: `cidx query "code that..." --quiet`
❌ "What is dependency injection?" → Can answer directly (general concept)

**ALWAYS USE --quiet FLAG**: This provides cleaner output without headers, making it easier to process results."""

    def _build_help_output(self) -> str:
        """Build the complete CIDX help output section."""
        return """📖 COMPLETE CIDX QUERY COMMAND REFERENCE

```
Usage: cidx query [OPTIONS] QUERY

Search the indexed codebase using semantic similarity.

Performs AI-powered semantic search across your indexed code.
Uses vector embeddings to find conceptually similar code.

SEARCH CAPABILITIES:
  • Semantic search: Finds conceptually similar code
  • Natural language: Describe what you're looking for
  • Code patterns: Search for specific implementations
  • Git-aware: Searches within current project/branch context

FILTERING OPTIONS:
  • Language: --language python (searches only Python files)
  • Path: --path */tests/* (searches only test directories)
  • Score: --min-score 0.8 (only high-confidence matches)
  • Limit: --limit 20 (more results)
  • Accuracy: --accuracy high (higher accuracy, slower search)

Options:
  -l, --limit INTEGER             Number of results to return (default: 10)
  --language TEXT                 Filter by programming language (e.g., python, javascript)
  --path TEXT                     Filter by file path pattern (e.g., */tests/*)
  --min-score FLOAT               Minimum similarity score (0.0-1.0)
  --accuracy [fast|balanced|high] Search accuracy profile
  -q, --quiet                     Quiet mode - only show results, no headers
```

**🎯 SUPPORTED LANGUAGES** (use exact names for --language filter):
- **Backend**: `python`, `java`, `csharp`, `cpp`, `c`, `go`, `rust`, `php`
- **Frontend**: `javascript`, `typescript`, `html`, `css`, `vue`  
- **Mobile**: `swift`, `kotlin`, `dart`
- **Scripts**: `shell`, `sql`, `markdown`, `yaml`, `json`"""

    def _build_strategic_usage(self) -> str:
        """Build strategic usage guidelines."""
        return """🚀 STRATEGIC USAGE PATTERNS

**SEARCH BEST PRACTICES**:
- Use natural language queries that match developer intent
- Try multiple search terms if first search doesn't yield results
- Search for both implementation AND usage patterns
- Use specific technical terms from the domain/framework
- Search for error messages, function names, class names, etc.

**QUERY EFFECTIVENESS**:
- Instead of: "authentication"
- Try: "login user authentication", "auth middleware", "token validation"

**FILTERING STRATEGIES**:
- `--language python --quiet` - Focus on specific language
- `--path "*/tests/*" --quiet` - Find test patterns
- `--min-score 0.8 --quiet` - High-confidence matches only
- `--limit 20 --quiet` - Broader exploration
- `--accuracy high --quiet` - Maximum precision for complex queries

**📊 UNDERSTANDING SCORES**:
- **Score 0.9-1.0**: Highly relevant, exact concept matches
- **Score 0.7-0.8**: Very relevant, closely related implementations
- **Score 0.5-0.6**: Moderately relevant, similar patterns  
- **Score 0.3-0.4**: Loosely related, might provide context
- **Score < 0.3**: Minimal relevance, usually not useful"""

    def _build_examples(self) -> str:
        """Build comprehensive examples section."""
        return """💡 PRACTICAL EXAMPLES (ALWAYS USE --quiet)

**Concept Discovery**:
- `cidx query "authentication mechanisms" --quiet`
- `cidx query "error handling patterns" --quiet`  
- `cidx query "data validation logic" --quiet`
- `cidx query "configuration management" --quiet`

**Implementation Finding**:
- `cidx query "API endpoint handlers" --language python --quiet`
- `cidx query "database queries" --language sql --limit 15 --quiet`
- `cidx query "async operations" --min-score 0.7 --quiet`
- `cidx query "REST API POST endpoint" --quiet`

**Testing & Quality**:
- `cidx query "unit test examples" --path "*/tests/*" --quiet`
- `cidx query "mock data creation" --limit 10 --quiet`
- `cidx query "integration test setup" --quiet`

**Architecture Exploration**:
- `cidx query "dependency injection setup" --quiet`
- `cidx query "microservice communication" --quiet`
- `cidx query "design patterns observer" --quiet`

**Multi-Step Discovery**:
1. Broad concept: `cidx query "user management" --quiet`
2. Narrow down: `cidx query "user authentication" --min-score 0.8 --quiet`
3. Find related: `cidx query "user permissions" --limit 5 --quiet`

**✅ SEMANTIC SEARCH vs ❌ TEXT SEARCH COMPARISON**:
✅ `cidx query "user authentication" --quiet` → Finds login, auth, security, credentials, sessions
❌ `grep "auth"` → Only finds literal "auth" text, misses related concepts

✅ `cidx query "error handling" --quiet` → Finds exceptions, try-catch, error responses, logging  
❌ `grep "error"` → Only finds "error" text, misses exception handling patterns"""

    def _build_advanced_patterns(self) -> str:
        """Build advanced search patterns for comprehensive level."""
        return """🔬 ADVANCED SEARCH STRATEGIES

**Cross-Reference Analysis**:
1. Find implementations: `cidx query "payment processing" --quiet`
2. Find tests: `cidx query "payment processing" --path "*/tests/*" --quiet`
3. Find config: `cidx query "payment configuration" --quiet`

**Language-Specific Exploration**:
1. Backend: `cidx query "REST API design" --language python --quiet`
2. Frontend: `cidx query "API consumption" --language javascript --quiet`
3. Database: `cidx query "data persistence" --language sql --quiet`

**Accuracy-Driven Discovery**:
1. Quick exploration: `cidx query "caching mechanisms" --accuracy fast --limit 20 --quiet`
2. Precise analysis: `cidx query "security vulnerabilities" --accuracy high --min-score 0.8 --quiet`
3. Balanced research: `cidx query "design patterns" --accuracy balanced --quiet`

**Progressive Refinement**:
1. Start broad: `cidx query "web framework" --quiet`
2. Add filters: `cidx query "web framework routing" --language python --quiet`
3. Increase precision: `cidx query "Flask routing decorators" --min-score 0.8 --quiet`"""


def create_cidx_instructions(
    codebase_dir: Optional[Path] = None,
    approach: str = "balanced",
    include_advanced: bool = False,
) -> str:
    """Convenience function to create CIDX instructions.

    Args:
        codebase_dir: Path to codebase for citations
        approach: "minimal", "balanced", or "comprehensive"
        include_advanced: Whether to include advanced patterns

    Returns:
        Formatted CIDX instruction string
    """
    builder = CidxInstructionBuilder(codebase_dir)

    if approach == "minimal":
        return builder.build_instructions(
            instruction_level="minimal",
            include_help_output=False,
            include_examples=True,
            include_advanced_patterns=False,
        )
    elif approach == "comprehensive":
        return builder.build_instructions(
            instruction_level="comprehensive",
            include_help_output=True,
            include_examples=True,
            include_advanced_patterns=True,
        )
    else:  # balanced
        return builder.build_instructions(
            instruction_level="balanced",
            include_help_output=True,
            include_examples=True,
            include_advanced_patterns=include_advanced,
        )

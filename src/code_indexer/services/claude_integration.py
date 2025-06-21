"""
Claude Code SDK integration service for RAG-based code analysis.

Provides intelligent code analysis using semantic search results and Claude AI.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .rag_context_extractor import RAGContextExtractor, CodeContext

# Claude CLI integration - no SDK required
CLAUDE_SDK_AVAILABLE = False  # We use CLI instead of SDK

logger = logging.getLogger(__name__)


@dataclass
class ClaudeAnalysisResult:
    """Result from Claude analysis."""

    response: str
    contexts_used: int
    total_context_lines: int
    search_query: str
    success: bool = True
    error: Optional[str] = None


class ClaudeIntegrationService:
    """Service for integrating Claude Code SDK with semantic search results."""

    def __init__(self, codebase_dir: Path, project_name: str = ""):
        """Initialize the Claude integration service.

        Args:
            codebase_dir: Root directory of the codebase
            project_name: Name of the project for context
        """
        # Claude CLI integration - no SDK required
        pass

        self.codebase_dir = Path(codebase_dir)
        self.project_name = project_name
        self.context_extractor = RAGContextExtractor(codebase_dir)

    def create_analysis_prompt(
        self,
        user_query: str,
        contexts: List[CodeContext],
        project_info: Optional[Dict[str, Any]] = None,
        enable_exploration: bool = True,
    ) -> str:
        """Create an optimized prompt for Claude analysis.

        Args:
            user_query: The user's question about the code
            contexts: List of extracted code contexts
            project_info: Optional project metadata (git info, etc.)
            enable_exploration: Whether to encourage file exploration

        Returns:
            Formatted prompt string for Claude
        """
        # Determine exploration depth based on user query
        exploration_depth = self._determine_exploration_depth(user_query)

        # Build semantic search tool instruction
        tool_instruction = self._create_tool_instruction(
            enable_exploration, exploration_depth
        )

        # Build project context
        project_context = self._create_project_context(project_info)

        # Format code contexts
        if contexts:
            formatted_contexts = self.context_extractor.format_contexts_for_prompt(
                contexts,
                include_line_numbers=True,
                max_context_length=40000,  # Leave room for other prompt parts
            )
        else:
            formatted_contexts = "No specific code contexts found for this query."

        # Build exploration instructions based on depth
        exploration_instructions = self._create_exploration_instructions(
            exploration_depth
        )

        # Build the complete prompt
        prompt = f"""You are an expert code analyst working with the {self.project_name or "this"} codebase. You have access to semantic search capabilities and can explore files as needed.

🔬 SCIENTIFIC EVIDENCE REQUIREMENT:
Treat this analysis like a scientific paper - ALL assertions must be backed by specific evidence from the source code. Every claim you make MUST include markdown links to exact source files and line numbers. No assertion is valid without proper citation to the codebase.

REQUIRED CITATION FORMAT:
- Use markdown links: [description](file_path:line_number) or [description](file_path:line_start-line_end)
- Examples: [UserService class](src/services/user.py:45), [authentication logic](auth/login.py:123-145)
- When referencing multiple files: cite ALL relevant files
- When explaining flows: cite EVERY step with specific file/line references
- When creating diagrams: include file/line citations in diagram elements

{tool_instruction}

{project_context}

USER QUESTION:
{user_query}

SEMANTIC SEARCH RESULTS:
{formatted_contexts}

{exploration_instructions}

Focus on providing accurate, actionable insights with MANDATORY evidence citations. Every technical statement requires a source code reference. No exceptions."""

        return prompt

    def _determine_exploration_depth(self, user_query: str) -> str:
        """Determine exploration depth based on user query language.

        Returns:
            'none' - No exploration, use only provided context
            'shallow' - One level deep exploration
            'deep' - No limits on exploration depth
        """
        query_lower = user_query.lower()

        # Quick response indicators
        quick_indicators = ["quick", "fast", "brief", "summary", "simple"]
        if any(indicator in query_lower for indicator in quick_indicators):
            return "none"

        # Deep analysis indicators
        deep_indicators = [
            "deep",
            "detailed",
            "accurate",
            "precise",
            "thorough",
            "comprehensive",
            "complete",
            "exhaustive",
            "in-depth",
        ]
        if any(indicator in query_lower for indicator in deep_indicators):
            return "deep"

        # Default to shallow exploration
        return "shallow"

    def _create_tool_instruction(
        self, enable_exploration: bool, exploration_depth: str = "shallow"
    ) -> str:
        """Create the semantic search tool instruction."""
        if not enable_exploration or exploration_depth == "none":
            return ""

        base_tools = """AVAILABLE TOOLS FOR CODEBASE EXPLORATION:

BUILT-IN SEMANTIC SEARCH TOOL:
You have access to a powerful semantic search tool that can find related code:
- `cidx query "search terms"` - Find semantically similar code throughout the codebase
- `cidx query "search terms" --limit N` - Limit results to N matches (default: 10)
- `cidx query "search terms" --language python` - Filter by specific language
- `cidx query "search terms" --file-pattern "*.py"` - Filter by file pattern
- `cidx query "search terms" --include-test` - Include test files in results
- `cidx query "search terms" --exclude-dir node_modules` - Exclude specific directories

QUERY TOOL RESULTS FORMAT:
The cidx query tool returns results with:
- **Relevance Score**: Similarity score (0.0-1.0, higher is more relevant)
- **File Path**: Full path to the file containing the match
- **Line Numbers**: Specific line range where the match was found
- **Content**: The actual code/text that matched your search
- **Context**: Surrounding code lines for better understanding

READ-ONLY FILE SYSTEM TOOLS:
- Read: Read any file in the codebase
- Glob: Find files using patterns (e.g., "src/**/*.py")  
- Grep: Search for specific patterns in files
- LS: List directory contents
- Task: Delegate complex file searches

NOTE: You cannot modify, edit, or execute any files (read-only access)

🔬 EVIDENCE CITATION REQUIREMENTS:
- When using any tool, immediately cite findings with [description](file_path:line_number)
- Never make claims about code without providing the exact source location
- Include file/line references in all explanations, diagrams, and flow descriptions
- Format citations as markdown links: [UserService.authenticate](src/services/user.py:123)
- For ranges: [authentication flow](auth/handlers.py:45-78)
- Treat every statement like a scientific paper - evidence required"""

        if exploration_depth == "shallow":
            return (
                base_tools
                + """

EXPLORATION GUIDELINES (LIMITED DEPTH):
- **Primary Focus**: Base analysis on provided semantic search results
- **Smart Exploration**: Use your judgment to decide how deep to explore based on the user's question
- **Prefer cidx**: When you need more code context, prioritize `cidx query` over other file exploration tools
- **Be Selective**: Explore only what's necessary to provide a complete answer

TOOL PREFERENCE ORDER (use in this priority):
1. **cidx query** - PREFERRED for finding related code, implementations, and examples
2. **Read** - For examining specific files identified by cidx or mentioned in search results  
3. **Glob** - Only when you need to find files by patterns that cidx might miss
4. **Grep** - Only for very specific text pattern searches within known files
5. **LS** - Only when you need to understand directory structure
6. **Task** - Only for complex multi-step file discovery that other tools can't handle

EXPLORATION APPROACH:
Use cidx query as your primary exploration tool. Other Claude Code tools (Read, Glob, Grep, LS, Task) are available but cidx query is specifically designed for semantic code discovery and should be your first choice for finding related code, implementations, patterns, and examples."""
            )

        else:  # exploration_depth == 'deep'
            return (
                base_tools
                + """

EXPLORATION GUIDELINES (UNLIMITED DEPTH):
- **Comprehensive Analysis**: Explore thoroughly to provide detailed, accurate answers
- **Smart Exploration**: Use your judgment to determine how extensively to explore based on the user's question
- **Prefer cidx**: Leverage `cidx query` extensively as your primary exploration tool
- **No Limits**: Explore as deeply as needed to provide complete insights

TOOL PREFERENCE ORDER (use in this priority):
1. **cidx query** - PREFERRED for finding all related code, implementations, patterns, and examples
2. **Read** - For examining specific files identified by cidx or for detailed code analysis
3. **Glob** - When you need to find files by patterns that semantic search might miss  
4. **Grep** - For specific text pattern searches within files
5. **LS** - When you need to understand directory structure and organization
6. **Task** - For complex multi-step file discovery or analysis workflows

EXPLORATION APPROACH:
Use cidx query extensively as your primary exploration tool to discover related code throughout the codebase. Other Claude Code tools (Read, Glob, Grep, LS, Task) are available for specific needs, but cidx query's semantic search capabilities make it the most powerful tool for code discovery and should be your go-to choice."""
            )

    def _create_exploration_instructions(self, exploration_depth: str) -> str:
        """Create analysis instructions based on exploration depth."""
        if exploration_depth == "none":
            return """ANALYSIS INSTRUCTIONS:
1. **Provided Context Only**: Base your entire answer on the semantic search results provided above
2. **No Exploration**: Do not use any file exploration tools (Read, Glob, Grep, cidx query)
3. **MANDATORY Citations**: Every single assertion MUST include markdown links [description](file_path:line_number)
4. **Evidence-Based Claims**: No statement about code behavior, structure, or functionality without citing exact source location
5. **Scientific Rigor**: Treat every claim like a scientific paper citation - provide the evidence reference
6. **Quick Response**: Provide a direct answer based solely on the given context, but with full citations
7. **Acknowledge Limitations**: If the provided context is insufficient, state what additional information would be needed"""

        elif exploration_depth == "shallow":
            return """ANALYSIS INSTRUCTIONS:
1. **Primary Analysis**: Base your answer on the provided semantic search results above - this should be your main source
2. **MANDATORY Evidence Citations**: Every assertion requires [description](file_path:line_number) markdown links
3. **Scientific Standards**: Each claim about code behavior, structure, or relationships MUST cite exact source location
4. **Limited Exploration**: Only explore files directly referenced in the search results (imports, includes, etc.)
5. **Citation-Driven Exploration**: When exploring, immediately cite what you find with file/line references
6. **One Level Deep**: Keep exploration to ONE LEVEL DEEP - avoid broad codebase traversal
7. **Targeted cidx**: Use `cidx query` sparingly for clarifying specific concepts, always citing results
8. **Evidence-Based Examples**: Include concrete code examples with mandatory citations to source files/lines
9. **No Unsupported Claims**: If you cannot cite a source location, do not make the claim
10. **Git-Aware Analysis**: If exploring git repositories, use git diff/log commands to understand code changes and evolution"""

        else:  # exploration_depth == 'deep'
            return """ANALYSIS INSTRUCTIONS:
1. **Comprehensive Analysis**: Explore the codebase thoroughly to provide detailed, accurate insights
2. **SCIENTIFIC RIGOR**: Every single assertion MUST include [description](file_path:line_number) citations
3. **Multi-Source Evidence**: Use provided search results as starting point, cite ALL sources extensively
4. **Deep Exploration with Citations**: Follow all references, dependencies, and related code, citing each discovery
5. **Extensive cidx Usage**: Use `cidx query` to find all related implementations, patterns, and usages - cite every finding
6. **Cross-Reference Documentation**: Look for relationships between different parts of the codebase, cite ALL connections
7. **Complete Context with Evidence**: Read relevant files, tests, documentation, and examples - cite every reference
8. **Evidence-Rich Examples**: Provide comprehensive code examples with mandatory source file/line citations
9. **Research Paper Standards**: Treat this like academic research - no claim without evidence citation
10. **Citation Completeness**: Include file paths, line numbers, and full context for EVERY single reference
11. **Flow Documentation**: When explaining processes or flows, cite each step with specific file/line references
12. **Git Repository Exploration**: Leverage git commands extensively for change analysis, history exploration, and branch comparisons
13. **Historical Context**: When analyzing code evolution, use git log/blame to understand development timeline and decision context"""

    def _create_project_context(self, project_info: Optional[Dict[str, Any]]) -> str:
        """Create project context information."""
        if not project_info:
            return f"PROJECT: {self.project_name or 'Code Analysis'}\nWORKING DIRECTORY: {self.codebase_dir}\n"

        context_parts = [
            f"PROJECT: {self.project_name or project_info.get('project_id', 'Unknown')}"
        ]
        context_parts.append(f"WORKING DIRECTORY: {self.codebase_dir}")

        if project_info.get("git_available"):
            context_parts.append(
                f"GIT BRANCH: {project_info.get('current_branch', 'unknown')}"
            )
            commit = project_info.get("current_commit", "unknown")
            if commit != "unknown" and len(commit) > 8:
                commit = commit[:8] + "..."
            context_parts.append(f"GIT COMMIT: {commit}")

        # Add git-aware capabilities section if git is available
        if project_info.get("git_available"):
            context_parts.append("")
            context_parts.append("🔧 GIT-AWARE ANALYSIS CAPABILITIES:")
            context_parts.append(
                "You are running on a Git repository and have access to advanced git tools:"
            )
            context_parts.append(
                "- `git diff [commit1]..[commit2]` - Compare code changes between commits/branches/tags"
            )
            context_parts.append(
                "- `git diff [commit]` - Show changes in working directory vs specific commit"
            )
            context_parts.append(
                "- `git log --oneline [file]` - View commit history for specific files"
            )
            context_parts.append(
                "- `git show [commit]:[file]` - View file content at specific commit"
            )
            context_parts.append(
                "- `git blame [file]` - Show line-by-line authorship and commit info"
            )
            context_parts.append(
                "- `git diff --name-only [commit1]..[commit2]` - List changed files between commits"
            )
            context_parts.append(
                "- `git merge-base [branch1] [branch2]` - Find common ancestor commit"
            )
            context_parts.append(
                "- `git branch --contains [commit]` - Find branches containing a commit"
            )
            context_parts.append("")
            context_parts.append("🎯 SUGGESTED GIT ANALYSIS WORKFLOWS:")
            context_parts.append(
                "1. **Change Impact Analysis**: Use `git diff --name-only` + `git diff` to analyze scope and impact"
            )
            context_parts.append(
                "2. **Branch Comparison**: Use `git merge-base` + `git diff` to compare branch divergence"
            )
            context_parts.append(
                "3. **Historical Analysis**: Use `git log` + `git show` to understand code evolution"
            )
            context_parts.append(
                "4. **File Evolution**: Use `git log --follow` + `git blame` to trace file history"
            )
            context_parts.append(
                "5. **Working Directory Analysis**: Use `git status` + `git diff` for uncommitted changes"
            )

        return "\n".join(context_parts) + "\n"

    def run_analysis(
        self, user_query: str, search_results: List[Dict[str, Any]], **kwargs
    ) -> ClaudeAnalysisResult:
        """Run Claude analysis using CLI subprocess to avoid SDK JSON bugs."""
        logger.info(
            "Using Claude CLI subprocess approach to avoid SDK JSON serialization issues"
        )

        # Extract contexts for the prompt
        context_lines = kwargs.get("context_lines", 500)
        contexts = self.context_extractor.extract_context_from_results(
            search_results,
            context_lines=context_lines,
            ensure_all_files=True,
        )

        return self._run_claude_cli_analysis(user_query, contexts, **kwargs)

    def _run_claude_cli_analysis(
        self, user_query: str, contexts: List[CodeContext], **kwargs
    ) -> ClaudeAnalysisResult:
        """Run Claude analysis using direct CLI subprocess call."""
        import subprocess

        # Check if streaming is requested
        stream_mode = kwargs.get("stream", False)
        if stream_mode:
            return self._run_claude_cli_streaming(user_query, contexts, **kwargs)

        try:
            # Use the rich prompt system with enhanced tool guidance
            # Get project info for context
            project_info = kwargs.get("project_info", {})
            enable_exploration = kwargs.get("enable_exploration", True)

            # Create the full rich prompt
            prompt = self.create_analysis_prompt(
                user_query=user_query,
                contexts=contexts,
                project_info=project_info,
                enable_exploration=enable_exploration,
            )

            try:
                # Run Claude CLI directly with prompt as stdin
                cmd = [
                    "claude",
                    "--print",  # Non-interactive mode
                    "--add-dir",
                    str(self.codebase_dir),  # Allow access to codebase
                ]

                logger.debug(f"Running Claude CLI: {' '.join(cmd)}")

                result = subprocess.run(
                    cmd,
                    input=prompt,  # Send prompt via stdin
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    cwd=str(self.codebase_dir),
                )

                if result.returncode == 0:
                    response = result.stdout.strip()
                    logger.info("Claude CLI analysis completed successfully")

                    return ClaudeAnalysisResult(
                        response=response,
                        contexts_used=len(contexts),
                        total_context_lines=sum(
                            ctx.line_end - ctx.line_start + 1 for ctx in contexts
                        ),
                        search_query=user_query,
                        success=True,
                    )
                else:
                    error_msg = result.stderr.strip() or "Unknown CLI error"
                    logger.error(f"Claude CLI failed: {error_msg}")

                    return ClaudeAnalysisResult(
                        response="",
                        contexts_used=0,
                        total_context_lines=0,
                        search_query=user_query,
                        success=False,
                        error=f"Claude CLI error: {error_msg}",
                    )

            finally:
                pass  # No temp file to clean up

        except subprocess.TimeoutExpired:
            logger.error("Claude CLI analysis timed out")
            return ClaudeAnalysisResult(
                response="",
                contexts_used=0,
                total_context_lines=0,
                search_query=user_query,
                success=False,
                error="Claude CLI analysis timed out after 5 minutes",
            )
        except Exception as e:
            logger.error(f"Claude CLI analysis failed: {e}")
            return ClaudeAnalysisResult(
                response="",
                contexts_used=0,
                total_context_lines=0,
                search_query=user_query,
                success=False,
                error=f"CLI execution error: {str(e)}",
            )

    def _run_claude_cli_streaming(
        self, user_query: str, contexts: List[CodeContext], **kwargs
    ) -> ClaudeAnalysisResult:
        """Run Claude analysis with streaming output using CLI subprocess."""
        import subprocess
        import json
        from rich.console import Console
        from rich.markdown import Markdown

        try:
            # Get project info for context
            project_info = kwargs.get("project_info", {})
            enable_exploration = kwargs.get("enable_exploration", True)
            quiet = kwargs.get("quiet", False)

            # Create the full rich prompt
            prompt = self.create_analysis_prompt(
                user_query=user_query,
                contexts=contexts,
                project_info=project_info,
                enable_exploration=enable_exploration,
            )

            # Run Claude CLI with streaming JSON output
            cmd = [
                "claude",
                "--print",
                "--verbose",  # Required for stream-json
                "--output-format",
                "stream-json",
                "--add-dir",
                str(self.codebase_dir),
            ]

            logger.debug(f"Running Claude CLI streaming: {' '.join(cmd)}")

            # Start the process
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
            )

            # Send prompt and close stdin
            if process.stdin:
                process.stdin.write(prompt)
                process.stdin.close()

            # Set up console and live display with markdown buffer
            from rich.markdown import Markdown

            console = Console()
            accumulated_text = ""
            final_result = ""
            text_buffer = ""

            if not quiet:
                console.print("\n🤖 Claude Analysis Results")
                console.print("─" * 80)

            def _is_markdown_line(line: str) -> bool:
                """Quick check if line looks like markdown."""
                stripped = line.strip()
                return (
                    stripped.startswith("#")
                    or stripped.startswith("```")
                    or stripped.startswith("- ")
                    or stripped.startswith("* ")
                    or "**" in stripped
                    or "__" in stripped
                    or stripped.startswith("> ")
                )

            def _flush_buffer_with_formatting(buffer: str, console: Console) -> None:
                """Flush text buffer with appropriate formatting."""
                if not buffer:
                    return

                # Check if buffer contains markdown patterns
                lines = buffer.split("\n")
                has_markdown = any(_is_markdown_line(line) for line in lines)

                if has_markdown and len(buffer.strip()) > 20:
                    # Try to render as markdown
                    try:
                        markdown = Markdown(buffer)
                        console.print(markdown)
                        return
                    except Exception:
                        # Fall back to plain text if markdown rendering fails
                        pass

                # Plain text with basic markup enabled
                console.print(buffer, end="")

            # Process streaming output
            try:
                if process.stdout:
                    for line in process.stdout:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            # Parse streaming JSON
                            data = json.loads(line)

                            # Handle assistant messages with text content
                            if (
                                data.get("type") == "assistant"
                                and "message" in data
                                and "content" in data["message"]
                            ):
                                content_blocks = data["message"]["content"]
                                for block in content_blocks:
                                    # Look for text content blocks
                                    if (
                                        isinstance(block, dict)
                                        and block.get("type") == "text"
                                    ):
                                        text_chunk = block.get("text", "")
                                        if text_chunk:
                                            accumulated_text += text_chunk
                                            text_buffer += text_chunk

                                            # Check for natural break points to flush formatted content
                                            if (
                                                "\n\n" in text_buffer
                                                or text_buffer.endswith("\n```\n")
                                                or text_buffer.endswith("\n---\n")
                                                or len(text_buffer) > 500
                                            ):
                                                _flush_buffer_with_formatting(
                                                    text_buffer, console
                                                )
                                                text_buffer = ""
                                            else:
                                                # For short chunks without break points, print immediately
                                                if len(text_chunk) < 50 and not any(
                                                    c in text_chunk
                                                    for c in ["#", "*", "`", ">"]
                                                ):
                                                    console.print(text_chunk, end="")
                                                    text_buffer = text_buffer[
                                                        : -len(text_chunk)
                                                    ]  # Remove from buffer since printed

                            # Handle final result (if format provides it)
                            elif data.get("type") == "result":
                                final_result = data.get("result", accumulated_text)
                                if data.get("is_error"):
                                    logger.error(
                                        f"Claude CLI error: {data.get('error', 'Unknown error')}"
                                    )
                                    break

                        except json.JSONDecodeError:
                            # Handle non-JSON lines (shouldn't happen with stream-json)
                            console.print(line, markup=False)
                            accumulated_text += line + "\n"

                # Flush any remaining buffer content
                if text_buffer:
                    _flush_buffer_with_formatting(text_buffer, console)

                # Wait for process to complete
                process.wait()

                if process.returncode == 0:
                    if not quiet:
                        console.print("\n")
                        console.print("─" * 80)

                    return ClaudeAnalysisResult(
                        response=final_result or accumulated_text,
                        contexts_used=len(contexts),
                        total_context_lines=sum(
                            ctx.line_end - ctx.line_start + 1 for ctx in contexts
                        ),
                        search_query=user_query,
                        success=True,
                    )
                else:
                    stderr_output = process.stderr.read() if process.stderr else ""
                    logger.error(f"Claude CLI streaming failed: {stderr_output}")
                    return ClaudeAnalysisResult(
                        response="",
                        contexts_used=0,
                        total_context_lines=0,
                        search_query=user_query,
                        success=False,
                        error=f"Claude CLI streaming error: {stderr_output}",
                    )

            except Exception as e:
                process.terminate()
                logger.error(f"Streaming processing error: {e}")
                return ClaudeAnalysisResult(
                    response="",
                    contexts_used=0,
                    total_context_lines=0,
                    search_query=user_query,
                    success=False,
                    error=f"Streaming error: {str(e)}",
                )

        except Exception as e:
            logger.error(f"Claude CLI streaming setup failed: {e}")
            return ClaudeAnalysisResult(
                response="",
                contexts_used=0,
                total_context_lines=0,
                search_query=user_query,
                success=False,
                error=f"Streaming setup error: {str(e)}",
            )

    def _validate_and_debug_prompt(self, prompt: str, user_query: str) -> str:
        """Validate prompt for JSON serialization and provide debugging info."""
        import json
        import re

        logger.debug(f"Validating prompt for query: {user_query[:50]}...")
        logger.debug(f"Original prompt length: {len(prompt)} characters")

        # Basic JSON serialization test
        try:
            json.dumps(prompt)
            logger.debug("✓ Prompt passes basic JSON serialization")
        except (TypeError, ValueError, UnicodeDecodeError) as e:
            logger.error(f"✗ Prompt fails JSON serialization: {e}")

            # Analyze the specific issues
            self._analyze_prompt_issues(prompt, e)

            # Attempt to clean the prompt
            cleaned_prompt = self._clean_prompt_for_json(prompt)
            logger.warning(
                f"Attempting to use cleaned prompt (length: {len(cleaned_prompt)})"
            )
            return cleaned_prompt

        # Check for potentially problematic patterns
        issues = []

        # Check for extremely long lines that might cause issues
        lines = prompt.split("\n")
        max_line_length = max(len(line) for line in lines) if lines else 0
        if max_line_length > 10000:
            issues.append(f"Very long line detected: {max_line_length} characters")

        # Check for unusual characters
        non_printable = re.findall(r"[^\x20-\x7E\n\r\t]", prompt)
        if non_printable:
            unique_chars = set(non_printable)
            issues.append(
                f"Non-ASCII characters found: {[ord(c) for c in list(unique_chars)[:10]]}"
            )

        # Check total size
        if len(prompt) > 100000:  # 100KB
            issues.append(f"Very large prompt: {len(prompt)} characters")

        # Check for potential JSON escape issues
        if '"' in prompt:
            quote_count = prompt.count('"')
            issues.append(
                f"Contains {quote_count} quote characters (may need escaping)"
            )

        if "\\" in prompt:
            backslash_count = prompt.count("\\")
            issues.append(
                f"Contains {backslash_count} backslash characters (may need escaping)"
            )

        # Log analysis results
        if issues:
            logger.warning(f"Potential prompt issues detected: {'; '.join(issues)}")
        else:
            logger.debug("✓ No obvious prompt issues detected")

        # Test with a simplified Claude options-like structure
        try:
            test_structure = {
                "prompt": prompt,
                "max_turns": 5,
                "cwd": str(self.codebase_dir),
                "test": True,
            }
            json.dumps(test_structure)
            logger.debug("✓ Prompt works in Claude options-like structure")
        except Exception as e:
            logger.error(f"✗ Prompt fails in Claude options structure: {e}")
            # Try with cleaned prompt
            cleaned_prompt = self._clean_prompt_for_json(prompt)
            test_structure["prompt"] = cleaned_prompt
            try:
                json.dumps(test_structure)
                logger.warning("✓ Cleaned prompt works in Claude options structure")
                return cleaned_prompt
            except Exception as e2:
                logger.error(f"✗ Even cleaned prompt fails: {e2}")

        return prompt

    def _analyze_prompt_issues(self, prompt: str, error: Exception) -> None:
        """Analyze specific issues with prompt serialization."""
        logger.error("=== PROMPT ANALYSIS ===")
        logger.error(f"Error type: {type(error).__name__}")
        logger.error(f"Error message: {str(error)}")

        # Find problematic characters around error position if possible
        error_str = str(error)
        if "char" in error_str:
            import re

            char_match = re.search(r"char (\d+)", error_str)
            if char_match:
                pos = int(char_match.group(1))
                start = max(0, pos - 50)
                end = min(len(prompt), pos + 50)
                context = prompt[start:end]
                logger.error(f"Context around error position {pos}:")
                logger.error(f"'{context}'")
                logger.error(
                    f"Problematic character: '{prompt[pos]}' (ord: {ord(prompt[pos])})"
                )

        # Sample of prompt content
        logger.error("Prompt preview (first 500 chars):")
        logger.error(f"'{prompt[:500]}'")

        if len(prompt) > 500:
            logger.error("Prompt preview (last 500 chars):")
            logger.error(f"'{prompt[-500:]}'")

        # Character encoding analysis
        try:
            encoded = prompt.encode("utf-8")
            logger.error(f"UTF-8 encoding: {len(encoded)} bytes")
        except UnicodeEncodeError as e:
            logger.error(f"UTF-8 encoding fails: {e}")

        try:
            encoded = prompt.encode("ascii", errors="ignore")
            ascii_length = len(encoded)
            logger.error(
                f"ASCII-only length: {ascii_length} chars (vs {len(prompt)} original)"
            )
        except Exception as e:
            logger.error(f"ASCII encoding fails: {e}")

    def _clean_prompt_for_json(self, prompt: str) -> str:
        """Clean prompt to make it JSON-safe."""
        import re

        logger.debug("Cleaning prompt for JSON compatibility...")

        # Remove or replace problematic characters
        # Replace non-printable characters except newlines and tabs
        cleaned = re.sub(r"[^\x20-\x7E\n\r\t]", "?", prompt)

        # Limit extremely long lines
        lines = cleaned.split("\n")
        max_line_length = 5000
        lines = [
            (
                line[:max_line_length] + "...[truncated]"
                if len(line) > max_line_length
                else line
            )
            for line in lines
        ]
        cleaned = "\n".join(lines)

        # Limit total size
        max_total_length = 50000  # 50KB limit
        if len(cleaned) > max_total_length:
            # Try to keep the structure intact
            half_length = max_total_length // 2
            cleaned = (
                cleaned[:half_length]
                + "\n\n... [MIDDLE CONTENT TRUNCATED] ...\n\n"
                + cleaned[-half_length:]
            )

        # Escape problematic sequences
        cleaned = cleaned.replace("\\", "\\\\")
        cleaned = cleaned.replace('"', '\\"')

        logger.debug(f"Cleaned prompt length: {len(cleaned)} characters")
        return cleaned

    def clear_cache(self):
        """Clear any internal caches."""
        self.context_extractor.clear_cache()


def check_claude_sdk_availability() -> bool:
    """Check if Claude CLI is available."""
    import subprocess

    try:
        result = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False

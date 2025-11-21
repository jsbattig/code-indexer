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
    tool_usage_summary: Optional[str] = None
    tool_usage_stats: Optional[Dict[str, Any]] = None


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
        # Import the unified instruction builder
        from .cidx_instruction_builder import CidxInstructionBuilder

        # Determine exploration depth based on user query
        exploration_depth = self._determine_exploration_depth(user_query)

        # Create unified CIDX instructions using the builder
        cidx_builder = CidxInstructionBuilder(self.codebase_dir)

        # Use comprehensive instructions for RAG-first approach (with advanced patterns for deep exploration)
        instruction_level = (
            "comprehensive" if exploration_depth == "deep" else "balanced"
        )
        include_advanced = exploration_depth == "deep"

        # Skip CIDX instructions entirely if exploration is disabled
        if not enable_exploration or exploration_depth == "none":
            cidx_instructions = ""
        else:
            cidx_instructions = cidx_builder.build_instructions(
                instruction_level=instruction_level,
                include_help_output=True,
                include_examples=True,
                include_advanced_patterns=include_advanced,
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

        # Additional citation format guidance for RAG-first approach
        citation_guidance = f"""
EVIDENCE AND CITATION REQUIREMENTS:
File paths in contexts are FACTUAL EVIDENCE. Use them exactly for citations.

MANDATORY CITATION FORMAT WITH EXAMPLES:

WRONG (breaks clickability):
❌ [method definition](file://{self.codebase_dir}/src/services/auth.py:45)
❌ [user class](file://{self.codebase_dir}/tests/test_user.py:123-145)
❌ [config setup](file://{self.codebase_dir}/config.py:67)

CORRECT (clickable URLs):
✅ [method definition line 45](file://{self.codebase_dir}/src/services/auth.py)
✅ [user class lines 123-145](file://{self.codebase_dir}/tests/test_user.py)
✅ [config setup line 67](file://{self.codebase_dir}/config.py)

RULE: Line numbers go in the DESCRIPTION text, never in the URL path!
"""

        # Add evidence requirements
        evidence_requirements = self._create_evidence_requirements()

        # Build the complete prompt
        prompt = f"""You are an expert code analyst working with the {self.project_name or "this"} codebase. You have access to semantic search capabilities and can explore files as needed.

{cidx_instructions}

{evidence_requirements}

{citation_guidance}

{project_context}

USER QUESTION:
{user_query}

SEMANTIC SEARCH RESULTS:
{formatted_contexts}

{exploration_instructions}

Focus on providing accurate, actionable insights with MANDATORY evidence citations. Every technical statement requires a source code reference. No exceptions.

REMINDER: When creating links, NEVER put :line_numbers in the URL. Example:
WRONG: file:///.../file.py:123
RIGHT: [description line 123](file:///.../file.py)"""

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

    def _create_exploration_instructions(self, exploration_depth: str) -> str:
        """Create analysis instructions based on exploration depth."""
        if exploration_depth == "none":
            return """ANALYSIS INSTRUCTIONS:
1. **Provided Context Only**: Base your entire answer on the semantic search results provided above
2. **No Exploration**: Do not use any file exploration tools (Read, Glob, Grep, cidx query)
3. **MANDATORY Citations**: Every single assertion MUST include markdown links [description](file://{self.codebase_dir}/file_path:line_number)
4. **Evidence-Based Claims**: No statement about code behavior, structure, or functionality without citing exact source location
5. **Scientific Rigor**: Treat every claim like a scientific paper citation - provide the evidence reference
6. **Quick Response**: Provide a direct answer based solely on the given context, but with full citations
7. **Acknowledge Limitations**: If the provided context is insufficient, state what additional information would be needed"""

        elif exploration_depth == "shallow":
            return """🔍 SEMANTIC-FIRST ANALYSIS INSTRUCTIONS:
1. **Semantic Foundation**: Base analysis on provided semantic search results + targeted cidx queries
2. **MANDATORY Evidence Citations**: Every assertion requires [description](file://{self.codebase_dir}/file_path:line_number) markdown links
3. **Scientific Standards**: Each claim about code behavior, structure, or relationships MUST cite exact source location
4. **Smart Semantic Exploration**: Use additional `cidx query` searches to clarify concepts from initial results
5. **AVOID Text Search**: Do NOT use grep unless cidx fails completely for your search needs
6. **Citation-Driven Discovery**: When using cidx, immediately cite findings with file/line references
7. **Semantic Depth Control**: Keep to ONE LEVEL of semantic exploration - avoid endless rabbit holes
8. **File Reading Strategy**: Read files identified by semantic search, not random text-based discoveries
9. **Evidence-Based Examples**: Include concrete code examples with mandatory citations to source files/lines
10. **No Unsupported Claims**: If you cannot cite a source location, do not make the claim
11. **Semantic Validation**: If you need to verify findings, use additional cidx queries, not text searches
12. **Git-Aware Analysis**: Use git commands for change analysis when relevant to semantic understanding"""

        else:  # exploration_depth == 'deep'
            return """🎯 COMPREHENSIVE SEMANTIC ANALYSIS INSTRUCTIONS:
1. **Semantic-Driven Exploration**: Use extensive cidx queries as your primary discovery method for thorough analysis
2. **SCIENTIFIC RIGOR**: Every single assertion MUST include [description](file_path:line_number) citations
3. **Multi-Semantic Evidence**: Start with provided results, then use multiple cidx searches with different terms
4. **Deep Semantic Trails**: Follow conceptual relationships discovered through semantic search, citing each discovery
5. **Extensive cidx Strategy**: Use cidx query extensively with varied search terms to find ALL related code patterns
6. **Semantic Cross-Reference**: Use cidx to find relationships between different codebase areas, cite ALL connections
7. **Complete Semantic Context**: Read files discovered through semantic search, including tests and documentation
8. **Evidence-Rich Examples**: Provide comprehensive code examples with mandatory source file/line citations
9. **Research Paper Standards**: Treat this like academic research - no claim without evidence citation from semantic discovery
10. **Citation Completeness**: Include file paths, line numbers, and full context for EVERY semantic search finding
11. **Semantic Flow Documentation**: When explaining processes, use cidx to find each step, cite with specific file/line references
12. **Text Search as Last Resort**: Only use grep when cidx cannot find specific literal strings you need
13. **Git Repository + Semantic Analysis**: Combine git commands with semantic search for comprehensive code evolution understanding
14. **Semantic Validation**: Cross-check findings with additional cidx queries to ensure comprehensive coverage"""

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

    def _create_evidence_requirements(self) -> str:
        """Create general evidence and citation requirements for Claude."""
        return f"""🔬 EVIDENCE CITATION REQUIREMENTS

**SCIENTIFIC EVIDENCE REQUIREMENT**:
Treat this analysis like a scientific paper - ALL assertions must be backed by specific evidence from the source code. Every claim you make MUST include markdown links to exact source files and line numbers.

**CITATION FORMAT**:
- Immediately cite ALL cidx query findings with file:// URLs
- Format: [description with line info](file://{self.codebase_dir}/path/to/file.py)
- Include relevance scores in citations when useful  
- Never make claims about code without exact source citations
- Every technical assertion requires semantic search evidence

**MANDATORY WORKFLOW**:
1. **ALWAYS START WITH SEMANTIC SEARCH**: Use `cidx query` first for any code discovery
2. **READ SPECIFIC FILES**: Use Read for files identified by cidx
3. **CITE EVERYTHING**: Provide file:line citations for all findings
4. **FALLBACK ONLY**: Use text search only if cidx returns no relevant results

Remember: You have read-only access. You cannot modify, edit, or execute files."""

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

            if stream_mode:
                # Use streaming mode implementation
                return self._run_claude_cli_streaming(user_query, contexts, **kwargs)

            try:
                # Non-streaming mode
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

                    # Generate tool usage summary if tracking was requested (non-streaming mode)
                    tool_summary = None
                    tool_stats = None
                    show_claude_plan = kwargs.get("show_claude_plan", False)
                    if show_claude_plan:
                        # For non-streaming mode, provide a basic summary indicating no tool tracking occurred
                        tool_summary = "## Tool Usage Summary\n\nNo tool usage tracking available (streaming mode disabled).\nClaude used non-interactive mode for this analysis."
                        tool_stats = {
                            "total_events": 0,
                            "tools_used": [],
                            "operation_counts": {},
                        }

                    return ClaudeAnalysisResult(
                        response=response,
                        contexts_used=len(contexts),
                        total_context_lines=sum(
                            ctx.line_end - ctx.line_start + 1 for ctx in contexts
                        ),
                        search_query=user_query,
                        success=True,
                        tool_usage_summary=tool_summary,
                        tool_usage_stats=tool_stats,
                    )
                else:
                    error_msg = result.stderr.strip() or "Unknown CLI error"
                    logger.error(f"Claude CLI failed: {error_msg}")

                    # Generate tool usage summary if tracking was requested (error case)
                    tool_summary = None
                    tool_stats = None
                    show_claude_plan = kwargs.get("show_claude_plan", False)
                    if show_claude_plan:
                        tool_summary = "## Tool Usage Summary\n\nClaude CLI failed - no tool usage tracking available."
                        tool_stats = {
                            "total_events": 0,
                            "tools_used": [],
                            "operation_counts": {},
                        }

                    return ClaudeAnalysisResult(
                        response="",
                        contexts_used=0,
                        total_context_lines=0,
                        search_query=user_query,
                        success=False,
                        error=f"Claude CLI error: {error_msg}",
                        tool_usage_summary=tool_summary,
                        tool_usage_stats=tool_stats,
                    )

            finally:
                pass  # No temp file to clean up

        except subprocess.TimeoutExpired:
            logger.error("Claude CLI analysis timed out")

            # Generate tool usage summary if tracking was requested (timeout case)
            tool_summary = None
            tool_stats = None
            show_claude_plan = kwargs.get("show_claude_plan", False)
            if show_claude_plan:
                tool_summary = "## Tool Usage Summary\n\nClaude CLI timed out - no tool usage tracking available."
                tool_stats = {
                    "total_events": 0,
                    "tools_used": [],
                    "operation_counts": {},
                }

            return ClaudeAnalysisResult(
                response="",
                contexts_used=0,
                total_context_lines=0,
                search_query=user_query,
                success=False,
                error="Claude CLI analysis timed out after 5 minutes",
                tool_usage_summary=tool_summary,
                tool_usage_stats=tool_stats,
            )
        except Exception as e:
            logger.error(f"Claude CLI analysis failed: {e}")

            # Generate tool usage summary if tracking was requested (exception case)
            tool_summary = None
            tool_stats = None
            show_claude_plan = kwargs.get("show_claude_plan", False)
            if show_claude_plan:
                tool_summary = f"## Tool Usage Summary\n\nClaude CLI failed with exception: {str(e)}\nNo tool usage tracking available."
                tool_stats = {
                    "total_events": 0,
                    "tools_used": [],
                    "operation_counts": {},
                }

            return ClaudeAnalysisResult(
                response="",
                contexts_used=0,
                total_context_lines=0,
                search_query=user_query,
                success=False,
                error=f"CLI execution error: {str(e)}",
                tool_usage_summary=tool_summary,
                tool_usage_stats=tool_stats,
            )

    def _run_claude_cli_streaming(
        self, user_query: str, contexts: List[CodeContext], **kwargs
    ) -> ClaudeAnalysisResult:
        """Run Claude analysis with streaming output using CLI subprocess."""
        import subprocess
        import json
        from rich.console import Console
        from .claude_tool_tracking import (
            ToolUsageTracker,
            CommandClassifier,
            process_tool_use_event,
        )

        try:
            # Get project info for context
            project_info = kwargs.get("project_info", {})
            enable_exploration = kwargs.get("enable_exploration", True)
            quiet = kwargs.get("quiet", False)
            show_claude_plan = kwargs.get("show_claude_plan", False)

            # Initialize tool tracking if requested
            tool_usage_tracker = None
            command_classifier = None
            if show_claude_plan:
                tool_usage_tracker = ToolUsageTracker()
                command_classifier = CommandClassifier()

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

            console = Console(force_terminal=True, legacy_windows=False)
            accumulated_text = ""
            final_result = ""
            text_buffer = ""
            last_output_was_text = False  # Track if we just printed text content

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
                nonlocal last_output_was_text
                if not buffer:
                    return

                # Check if buffer contains markdown patterns
                lines = buffer.split("\n")
                has_markdown = any(_is_markdown_line(line) for line in lines)

                if has_markdown and len(buffer.strip()) > 20:
                    # Handle file:// links specially, then process markdown
                    try:
                        # Split content into parts and handle file:// links separately
                        processed_content = self._render_content_with_file_links(
                            buffer, console
                        )
                        if processed_content:
                            last_output_was_text = True
                            return
                    except Exception:
                        # Fall back to plain text if markdown rendering fails
                        pass

                # Plain text with basic markup enabled
                console.print(buffer, end="")
                last_output_was_text = True

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

                            # Handle assistant messages with text content and tool usage
                            if (
                                data.get("type") == "assistant"
                                and "message" in data
                                and "content" in data["message"]
                            ):
                                content_blocks = data["message"]["content"]
                                for block in content_blocks:
                                    # Handle text content blocks
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
                                                    last_output_was_text = True
                                                    text_buffer = text_buffer[
                                                        : -len(text_chunk)
                                                    ]  # Remove from buffer since printed

                                    # Handle tool usage blocks
                                    elif (
                                        isinstance(block, dict)
                                        and block.get("type") == "tool_use"
                                        and show_claude_plan
                                        and tool_usage_tracker
                                        and command_classifier
                                    ):
                                        try:
                                            # Check if we need a newline (pending text OR recent text output)
                                            needs_newline = (
                                                bool(text_buffer.strip())
                                                or last_output_was_text
                                            )

                                            # Flush any pending text first
                                            if text_buffer:
                                                _flush_buffer_with_formatting(
                                                    text_buffer, console
                                                )
                                                text_buffer = ""

                                            # Process tool usage event
                                            tool_event = process_tool_use_event(
                                                block, command_classifier
                                            )
                                            tool_usage_tracker.track_tool_start(
                                                tool_event
                                            )

                                            # Display tool usage (add newline if we had recent text output)
                                            if not quiet:
                                                prefix = "\n" if needs_newline else ""
                                                console.print(
                                                    f"{prefix}{tool_event.visual_cue} {tool_event.command_detail}",
                                                    style="cyan",
                                                )
                                                last_output_was_text = False  # Reset flag after tool output

                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to process tool_use event: {e}"
                                            )

                            # Handle user messages with tool results (track but don't display inline)
                            elif (
                                data.get("type") == "user"
                                and "message" in data
                                and "content" in data["message"]
                                and show_claude_plan
                                and tool_usage_tracker
                            ):
                                content_blocks = data["message"]["content"]
                                for block in content_blocks:
                                    if (
                                        isinstance(block, dict)
                                        and block.get("type") == "tool_result"
                                    ):
                                        try:
                                            # Process tool completion for tracking/summary only
                                            tool_result_data = {
                                                "tool_use_id": block.get("tool_use_id"),
                                                "is_error": block.get(
                                                    "is_error", False
                                                ),
                                                "content": block.get("content", ""),
                                            }
                                            tool_usage_tracker.track_tool_completion(
                                                tool_result_data
                                            )
                                            # No inline display - completion info will be in final summary

                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to process tool_result event: {e}"
                                            )

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

                # Generate tool usage summary if tracking was enabled (regardless of Claude CLI success)
                tool_summary = None
                tool_stats = None
                if show_claude_plan and tool_usage_tracker:
                    try:
                        from .claude_tool_tracking import ClaudePlanSummary

                        summary_generator = ClaudePlanSummary()
                        all_events = tool_usage_tracker.get_all_events()
                        tool_summary = summary_generator.generate_complete_summary(
                            all_events
                        )
                        tool_stats = tool_usage_tracker.get_summary_stats()
                    except Exception as e:
                        logger.warning(f"Failed to generate tool usage summary: {e}")
                        # Provide minimal summary if generation fails
                        tool_summary = "Tool usage tracking was enabled but summary generation failed."
                        tool_stats = {
                            "total_events": 0,
                            "tools_used": [],
                            "operation_counts": {},
                        }

                if process.returncode == 0:
                    # Display final tool usage summary with proper formatting (only on success)
                    if not quiet and tool_summary:
                        console.print("\n")
                        console.print("─" * 80)
                        console.print(
                            "🤖 Claude's Problem-Solving Approach",
                            style="bold cyan",
                        )
                        console.print("─" * 80)
                        try:
                            # Special handling for tool usage statistics to ensure proper line breaks
                            if "📊 Tool Usage Statistics" in tool_summary:
                                lines = tool_summary.split("\n")
                                in_stats_section = False

                                for line in lines:
                                    stripped_line = line.strip()

                                    if "📊 Tool Usage Statistics" in stripped_line:
                                        in_stats_section = True
                                        console.print(
                                            "\n" + stripped_line,
                                            style="bold cyan",
                                        )
                                        continue

                                    if in_stats_section and stripped_line:
                                        if "Operation Breakdown:" in stripped_line:
                                            console.print(
                                                "\n" + stripped_line,
                                                style="bold",
                                            )
                                        elif any(
                                            emoji in stripped_line
                                            for emoji in ["🔍✨", "😞", "📄"]
                                        ):
                                            # Operation breakdown items
                                            console.print("  " + stripped_line)
                                        elif (
                                            stripped_line
                                            and not stripped_line.startswith("##")
                                        ):
                                            # Regular statistics lines
                                            console.print("  " + stripped_line)
                                        else:
                                            console.print("")
                                    elif stripped_line:
                                        # Regular narrative content - use markdown for this part
                                        if any(
                                            md_char in line
                                            for md_char in [
                                                "**",
                                                "_",
                                                "#",
                                                "`",
                                                "*",
                                            ]
                                        ):
                                            # Process line to improve link readability
                                            processed_line = (
                                                self._process_markdown_for_readability(
                                                    line
                                                )
                                            )
                                            console.print(processed_line)
                                        else:
                                            console.print(line)
                                    else:
                                        console.print("")
                            else:
                                # Regular markdown processing for non-statistics content
                                try:
                                    # Process for better readability
                                    processed_summary = (
                                        self._process_markdown_for_readability(
                                            tool_summary
                                        )
                                    )
                                    console.print(processed_summary)
                                except Exception as e:
                                    # Fallback to plain text if markdown rendering fails
                                    logger.warning(f"Markdown rendering failed: {e}")
                                    console.print(tool_summary)
                        except Exception as e:
                            logger.warning(
                                f"Failed to generate tool usage summary: {e}"
                            )

                    if not quiet and not (show_claude_plan and tool_summary):
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
                        tool_usage_summary=tool_summary,
                        tool_usage_stats=tool_stats,
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
                        tool_usage_summary=tool_summary,
                        tool_usage_stats=tool_stats,
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
                    tool_usage_summary=tool_summary,
                    tool_usage_stats=tool_stats,
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

    def _process_markdown_for_readability(self, line: str) -> str:
        """Process markdown line to improve link readability while preserving file path links."""
        import re

        # Convert markdown links [text](url) for better readability
        def replace_link(match):
            text = match.group(1)
            url = match.group(2)

            # For file:// URLs, use a more terminal-friendly format
            if url.startswith("file://"):
                # Extract the actual file path from file:// URL
                file_path = url[7:]  # Remove 'file://' prefix
                # Format as colored clickable link with a clear visual indicator
                return f"📁 {text} [dim cyan]({file_path})[/dim cyan]"
            elif url.startswith(("src/", "/", "./")):
                # For relative/absolute paths, make them visually distinct
                return f"📄 {text} [dim cyan]({url})[/dim cyan]"
            elif ":" in url and not url.startswith(("http", "https", "ftp")):
                # For other path-like URLs
                return f"📄 {text} [dim cyan]({url})[/dim cyan]"
            else:
                # For external URLs, remove the link to avoid dark colors but show URL
                return f"{text} ({url})"

        # Replace markdown links with more readable format
        processed = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, line)

        return processed

    def _process_file_links_for_display(self, text: str) -> str:
        """Process file:// links to make them more readable in terminal output."""
        import re

        # Pattern to match [text](file://path) format
        def replace_file_link(match):
            text_part = match.group(1)
            url = match.group(2)

            if url.startswith("file://"):
                # Extract actual file path
                file_path = url[7:]  # Remove 'file://' prefix
                # Create a simple, readable format without complex markup
                # Show the description as clickable text with file path in parentheses
                return f"[bright_blue]{text_part}[/bright_blue] [dim cyan]({file_path})[/dim cyan]"
            else:
                # Keep other URLs as-is
                return f"[{text_part}]({url})"

        # Replace file:// links
        processed = re.sub(r"\[([^\]]+)\]\((file://[^)]+)\)", replace_file_link, text)

        return processed

    def _preprocess_file_links(self, text: str) -> str:
        """Pre-process file:// links to keep them clickable but display better."""
        import re

        def replace_file_link(match):
            text_part = match.group(1)
            url = match.group(2)

            if url.startswith("file://"):
                # Keep the file:// URL for clickability but improve the display
                # Use HTML-style link that Rich can handle better
                return f'<a href="{url}">{text_part}</a>'
            else:
                # Keep other URLs as regular markdown links
                return f"[{text_part}]({url})"

        # Replace file:// links with HTML links that Rich can render
        processed = re.sub(r"\[([^\]]+)\]\((file://[^)]+)\)", replace_file_link, text)

        return processed

    def _render_content_with_file_links(self, content: str, console) -> bool:
        """Render content with special handling for file:// links."""
        import re
        from rich.text import Text

        # Find all file:// links in the content
        file_link_pattern = r"\[([^\]]+)\]\((file://[^)]+)\)"
        links = list(re.finditer(file_link_pattern, content))

        if not links:
            # No file links, process with Claude Code-style formatting
            self._print_claude_code_style(content, console)
            return True

        # When we have file links, we need to process the content carefully
        # Split content by file links and apply Claude Code formatting to each part
        from typing import Union, Tuple, List

        last_end = 0
        content_parts: List[Union[Tuple[str, str], Tuple[str, str, str, str]]] = []

        for match in links:
            # Get content before this link
            before_content = content[last_end : match.start()]
            if before_content.strip():
                content_parts.append(("text", before_content))

            # Add the file link as a special part
            text_part = match.group(1)
            url = match.group(2)
            file_path = url[7:]  # Remove 'file://' prefix
            content_parts.append(("link", text_part, url, file_path))

            last_end = match.end()

        # Add any remaining content after the last link
        remaining_content = content[last_end:]
        if remaining_content.strip():
            content_parts.append(("text", remaining_content))

        # Now render each part appropriately
        for part in content_parts:
            if part[0] == "text" and len(part) == 2:
                # Apply Claude Code formatting to text content
                self._print_claude_code_style(part[1], console)
            elif part[0] == "link" and len(part) == 4:
                # Render the file link specially
                text_part, url, file_path = part[1], part[2], part[3]
                link_text = Text()
                link_text.append(text_part, style=f"bright_blue link {url}")
                link_text.append(f" ({file_path})", style="dim cyan")
                console.print(link_text)

        return True

    def _post_process_rendered_links(self, rendered_text: str) -> str:
        """Post-process rendered markdown to improve file:// link display."""
        import re

        # Pattern to find file:// URLs in rendered text
        # This will match patterns like [text](file://path) that markdown didn't process
        def replace_file_link(match):
            text_part = match.group(1)
            url = match.group(2)

            if url.startswith("file://"):
                # Extract actual file path
                file_path = url[7:]  # Remove 'file://' prefix
                # Create a simple, readable format
                return f"\033[94m{text_part}\033[0m \033[2;36m({file_path})\033[0m"
            else:
                # Keep other URLs as-is
                return f"{text_part} ({url})"

        # Replace remaining file:// links that weren't processed by markdown
        processed = re.sub(
            r"\[([^\]]+)\]\((file://[^)]+)\)", replace_file_link, rendered_text
        )

        return processed

    def _print_claude_code_style(self, content: str, console) -> None:
        """Print content with Claude Code-style formatting (left-aligned, readable)."""
        lines = content.split("\n")

        for line in lines:
            stripped = line.strip()

            # Handle headers (## ###) - make them stand out but left-aligned
            if stripped.startswith("### "):
                header_text = stripped[4:].strip()
                console.print(f"\n{header_text}", style="bold cyan")
            elif stripped.startswith("## "):
                header_text = stripped[3:].strip()
                console.print(f"\n{header_text}", style="bold bright_cyan")
            elif stripped.startswith("# "):
                header_text = stripped[2:].strip()
                console.print(f"\n{header_text}", style="bold bright_white")

            # Handle code blocks
            elif stripped.startswith("```"):
                if stripped == "```":
                    console.print(line)  # Just print the fence
                else:
                    # Code block with language
                    lang = stripped[3:].strip()
                    console.print(f"```{lang}", style="dim")

            # Handle list items
            elif stripped.startswith("- ") or stripped.startswith("* "):
                bullet_content = stripped[2:].strip()
                # Process inline formatting in bullet content
                formatted_content = self._process_inline_formatting(bullet_content)
                console.print(f"  • {formatted_content}")

            # Handle numbered lists
            elif stripped and stripped[0].isdigit() and ". " in stripped:
                list_content = (
                    stripped.split(". ", 1)[1] if ". " in stripped else stripped
                )
                formatted_content = self._process_inline_formatting(list_content)
                console.print(f"  {stripped.split('.')[0]}. {formatted_content}")

            # Handle regular text with inline formatting
            elif stripped:
                formatted_content = self._process_inline_formatting(stripped)
                console.print(formatted_content)

            # Handle empty lines
            else:
                console.print()

    def _process_inline_formatting(self, text: str) -> str:
        """Process inline markdown formatting like **bold** and *italic* in Claude Code style."""
        import re

        # Handle bold **text**
        text = re.sub(r"\*\*([^*]+)\*\*", r"[bold]\1[/bold]", text)

        # Handle italic *text*
        text = re.sub(r"\*([^*]+)\*", r"[italic]\1[/italic]", text)

        # Handle inline code `text`
        text = re.sub(r"`([^`]+)`", r"[cyan]`\1`[/cyan]", text)

        return text

    def _matches_gitignore_pattern(
        self, path: Path, rel_path_str: str, pattern: str
    ) -> bool:
        """Check if a path matches a gitignore pattern."""
        import fnmatch

        # Handle directory patterns (ending with /)
        if pattern.endswith("/"):
            if path.is_dir():
                dir_pattern = pattern[:-1]
                if fnmatch.fnmatch(path.name, dir_pattern) or fnmatch.fnmatch(
                    rel_path_str, dir_pattern
                ):
                    return True
        else:
            # Handle file patterns
            if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(
                rel_path_str, pattern
            ):
                return True

            # Handle path-based patterns
            if "/" in pattern:
                if fnmatch.fnmatch(rel_path_str, pattern):
                    return True

        return False

    def get_project_structure(self, max_files: int = 1000) -> str:
        """Get full project structure as a tree-like listing.

        Args:
            max_files: Maximum number of files to include

        Returns:
            Formatted project structure string
        """
        from pathlib import Path

        structure_lines = []
        file_count = 0

        # Common ignore patterns (always applied)
        common_ignore_patterns = {
            ".git",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".coverage",
            "htmlcov",
            "experiments",
        }

        # Check if this is a git repository and load .gitignore
        gitignore_patterns = []
        is_git_repo = (self.codebase_dir / ".git").exists()

        if is_git_repo:
            gitignore_file = self.codebase_dir / ".gitignore"
            if gitignore_file.exists():
                try:
                    gitignore_content = gitignore_file.read_text(encoding="utf-8")
                    for line in gitignore_content.split("\n"):
                        line = line.strip()
                        # Skip empty lines and comments
                        if line and not line.startswith("#"):
                            gitignore_patterns.append(line)
                except Exception as e:
                    logger.warning(f"Failed to read .gitignore: {e}")

        def should_ignore(path: Path) -> bool:
            """Check if path should be ignored."""
            # Always ignore common patterns (these take precedence)
            for pattern in common_ignore_patterns:
                if pattern.startswith("*."):
                    if path.name.endswith(pattern[1:]):
                        return True
                elif pattern in str(path):
                    return True

            # If git-aware, check .gitignore patterns
            if is_git_repo and gitignore_patterns:
                # Get relative path from project root
                try:
                    rel_path = path.relative_to(self.codebase_dir)
                    rel_path_str = str(rel_path)

                    # Process gitignore patterns in order
                    is_ignored = False

                    for pattern in gitignore_patterns:
                        # Handle negation patterns (starting with !)
                        if pattern.startswith("!"):
                            # This is a negation pattern - if it matches, unignore the file
                            neg_pattern = pattern[1:]
                            if self._matches_gitignore_pattern(
                                path, rel_path_str, neg_pattern
                            ):
                                is_ignored = False
                        else:
                            # Regular ignore pattern
                            if self._matches_gitignore_pattern(
                                path, rel_path_str, pattern
                            ):
                                is_ignored = True

                    return is_ignored
                except ValueError:
                    # Path is not relative to codebase_dir, skip gitignore check
                    pass

            return False

        def add_directory(dir_path: Path, prefix: str = "", is_last: bool = True):
            """Recursively add directory structure."""
            nonlocal file_count

            if file_count >= max_files:
                return

            if should_ignore(dir_path):
                return

            try:
                items = sorted(
                    dir_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())
                )

                for i, item in enumerate(items):
                    if file_count >= max_files:
                        structure_lines.append(
                            f"{prefix}├── ... (truncated at {max_files} files)"
                        )
                        break

                    if should_ignore(item):
                        continue

                    is_last_item = i == len(items) - 1
                    connector = "└── " if is_last_item else "├── "

                    if item.is_file():
                        structure_lines.append(f"{prefix}{connector}{item.name}")
                        file_count += 1
                    else:
                        structure_lines.append(f"{prefix}{connector}{item.name}/")
                        extension = "    " if is_last_item else "│   "
                        add_directory(item, prefix + extension, is_last_item)

            except PermissionError:
                structure_lines.append(f"{prefix}├── [Permission Denied]")

        # Start with project root
        project_name = self.codebase_dir.name
        structure_lines.append(f"{project_name}/")
        add_directory(self.codebase_dir, "")

        return "\n".join(structure_lines)

    def create_claude_first_prompt(
        self,
        user_query: str,
        project_info: Optional[Dict[str, Any]] = None,
        include_project_structure: bool = True,
    ) -> str:
        """Create a prompt for claude-first approach (no RAG upfront).

        Args:
            user_query: The user's question about the code
            project_info: Optional project metadata (git info, etc.)
            include_project_structure: Whether to include full project structure

        Returns:
            Formatted prompt string for Claude
        """
        # Import the unified instruction builder
        from .cidx_instruction_builder import CidxInstructionBuilder

        # Build project context
        project_context = self._create_project_context(project_info)

        # Get project structure if requested
        project_structure = ""
        if include_project_structure:
            try:
                structure = self.get_project_structure()
                project_structure = f"""## PROJECT STRUCTURE
Here's the complete file structure of the codebase:

```
{structure}
```
"""
            except Exception as e:
                logger.warning(f"Failed to generate project structure: {e}")
                project_structure = (
                    "\n## PROJECT STRUCTURE\n(Unable to generate project structure)\n"
                )

        # Create unified CIDX instructions using the builder
        cidx_builder = CidxInstructionBuilder(self.codebase_dir)
        cidx_instructions = cidx_builder.build_instructions(
            instruction_level="balanced",
            include_help_output=True,
            include_examples=True,
            include_advanced_patterns=False,
        )

        # Add evidence requirements
        evidence_requirements = self._create_evidence_requirements()

        # Build the complete prompt
        prompt = f"""You are an expert code analyst working with the {self.project_name or "this"} codebase.

{cidx_instructions}

{evidence_requirements}

{project_context}{project_structure}

## USER QUESTION
{user_query}

Please analyze this question and use semantic search to find relevant code before providing your answer. Provide specific file and line citations for all claims."""

        return prompt

    def run_claude_first_analysis(
        self,
        user_query: str,
        project_info: Optional[Dict[str, Any]] = None,
        max_turns: int = 5,
        stream: bool = True,
        quiet: bool = False,
        show_claude_plan: bool = False,
        include_project_structure: bool = True,
    ) -> ClaudeAnalysisResult:
        """Run Claude analysis using claude-first approach (no RAG upfront).

        Args:
            user_query: The user's question about the code
            project_info: Optional project metadata (git info, etc.)
            max_turns: Maximum conversation turns
            stream: Whether to stream the response
            quiet: Whether to run in quiet mode
            show_claude_plan: Whether to show tool usage tracking
            include_project_structure: Whether to include full project structure

        Returns:
            ClaudeAnalysisResult with analysis
        """
        try:
            # Create claude-first prompt
            prompt = self.create_claude_first_prompt(
                user_query=user_query,
                project_info=project_info,
                include_project_structure=include_project_structure,
            )

            # Run Claude CLI analysis with empty contexts for claude-first approach
            return self._run_claude_cli_analysis(
                user_query=user_query,
                contexts=[],  # Empty contexts for claude-first approach
                prompt=prompt,
                max_turns=max_turns,
                stream=stream,
                quiet=quiet,
                show_claude_plan=show_claude_plan,
            )

        except Exception as e:
            logger.error(f"Claude first analysis failed: {e}")
            return ClaudeAnalysisResult(
                response="",
                contexts_used=0,
                total_context_lines=0,
                search_query=user_query,
                success=False,
                error=str(e),
            )

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

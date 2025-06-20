"""
Claude Code SDK integration service for RAG-based code analysis.

Provides intelligent code analysis using semantic search results and Claude AI.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass

try:
    from claude_code_sdk import query, ClaudeCodeOptions

    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

from .rag_context_extractor import RAGContextExtractor, CodeContext

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
        if not CLAUDE_SDK_AVAILABLE:
            raise ImportError(
                "Claude Code SDK not available. Install with: pip install claude-code-sdk"
            )

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
        # Build semantic search tool instruction
        tool_instruction = self._create_tool_instruction(enable_exploration)

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

        # Build the complete prompt
        prompt = f"""You are an expert code analyst working with the {self.project_name or 'this'} codebase. You have access to semantic search capabilities and can explore files as needed.

{tool_instruction}

{project_context}

USER QUESTION:
{user_query}

SEMANTIC SEARCH RESULTS:
{formatted_contexts}

ANALYSIS INSTRUCTIONS:
1. **Primary Analysis**: Base your answer on the provided semantic search results above - this should be your main source
2. **Code References**: Include specific file paths and line numbers when referencing code
3. **Limited Exploration**: Only explore files if directly referenced in the search results (imports, includes, etc.)
4. **Stay Focused**: Keep exploration to ONE LEVEL DEEP - avoid broad codebase traversal
5. **Quick Response**: Prioritize answering from provided context over extensive exploration
6. **Examples**: Include concrete code examples from the search results when relevant

Focus on providing accurate, actionable insights based primarily on the provided search results. Use minimal, targeted exploration only when necessary to clarify the provided context."""

        return prompt

    def _create_tool_instruction(self, enable_exploration: bool) -> str:
        """Create the semantic search tool instruction."""
        if not enable_exploration:
            return ""

        return """AVAILABLE TOOLS FOR LIMITED CODEBASE EXPLORATION:

READ-ONLY FILE SYSTEM TOOLS:
You have access to these tools for exploring files referenced in the search results:
- Read: Read any file mentioned in the search results or their imports
- Glob: Find related files using specific patterns (e.g., "dirname/*.py")
- Grep: Search for specific patterns in files
- LS: List contents of directories containing the search result files

EXPLORATION GUIDELINES (STAY FOCUSED):
- Focus primarily on the provided search results context
- Only explore files that are directly referenced in the search results (imports, includes, etc.)
- Limit exploration to ONE LEVEL DEEP from the initial results
- Read files that help clarify the search results, but avoid broad exploration
- You cannot modify, edit, or execute any files (read-only access)

FOCUSED EXPLORATION PATTERN:
1. Analyze the provided search results first
2. If needed, read files that are imported/referenced in those results
3. Use Glob only for files in the same directory as search results
4. Avoid deep directory traversal or broad searches
5. Answer based primarily on provided context + minimal targeted exploration"""

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

        return "\n".join(context_parts) + "\n"

    async def analyze_with_claude(
        self,
        user_query: str,
        search_results: List[Dict[str, Any]],
        context_lines: int = 500,
        max_turns: int = 5,
        project_info: Optional[Dict[str, Any]] = None,
        enable_exploration: bool = True,
        claude_options: Optional[ClaudeCodeOptions] = None,
    ) -> ClaudeAnalysisResult:
        """Analyze code using Claude with RAG context.

        Args:
            user_query: The user's question
            search_results: Results from semantic search
            context_lines: Lines of context around each match
            max_turns: Maximum conversation turns
            project_info: Project metadata
            enable_exploration: Whether to enable file exploration
            claude_options: Custom Claude options

        Returns:
            ClaudeAnalysisResult with analysis
        """
        try:
            # Extract contexts from search results
            # Ensure all file references are included by adjusting context size if needed
            contexts = self.context_extractor.extract_context_from_results(
                search_results,
                context_lines=context_lines,
                ensure_all_files=True,  # Prioritize including all files over context size
            )

            # Create analysis prompt
            prompt = self.create_analysis_prompt(
                user_query=user_query,
                contexts=contexts,
                project_info=project_info,
                enable_exploration=enable_exploration,
            )

            # TEMPORARY: Use simple prompt to avoid JSON issues
            prompt = f"You are a code analyst. Answer this question about the codebase: {user_query}\n\nProvided context:\n{self.context_extractor.format_contexts_for_prompt(contexts, include_line_numbers=True, max_context_length=10000) if contexts else 'No specific context found.'}"

            # Configure Claude options
            if claude_options is None:
                claude_options = ClaudeCodeOptions(
                    max_turns=1,
                    cwd=str(self.codebase_dir),
                    system_prompt="You are a code analyst. Analyze the code and answer the question.",
                )

            # Query Claude
            logger.info(f"Starting Claude analysis for query: {user_query[:100]}...")
            logger.debug(f"Prompt length: {len(prompt)} characters")
            logger.debug(f"Prompt preview: {prompt[:500]}...")

            response_parts = []
            message_count = 0

            async for message in query(prompt=prompt, options=claude_options):
                if hasattr(message, "content") and message.content:
                    # Extract text content from Claude SDK message
                    text_content = self._extract_text_from_message(message.content)
                    if text_content:
                        response_parts.append(text_content)
                        message_count += 1

                        # Log progress
                        if message_count % 2 == 0:
                            logger.info(
                                f"Received {message_count} messages from Claude..."
                            )

            # Combine response
            full_response = (
                "\n".join(response_parts)
                if response_parts
                else "No response received from Claude."
            )

            # Calculate stats
            total_lines = sum(
                context.line_end - context.line_start + 1 for context in contexts
            )

            logger.info(
                f"Claude analysis complete. Used {len(contexts)} contexts with {total_lines} total lines."
            )

            return ClaudeAnalysisResult(
                response=full_response,
                contexts_used=len(contexts),
                total_context_lines=total_lines,
                search_query=user_query,
                success=True,
            )

        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return ClaudeAnalysisResult(
                response="",
                contexts_used=0,
                total_context_lines=0,
                search_query=user_query,
                success=False,
                error=str(e),
            )

    def _extract_text_from_message(self, content) -> str:
        """Extract text content from Claude SDK message content."""
        try:
            # Handle different content types from Claude SDK
            if isinstance(content, str):
                return content

            # If content is a list of blocks
            if isinstance(content, (list, tuple)):
                text_parts = []
                for block in content:
                    if hasattr(block, "text"):
                        text_parts.append(str(block.text))
                    elif (
                        hasattr(block, "type")
                        and block.type == "text"
                        and hasattr(block, "content")
                    ):
                        text_parts.append(str(block.content))
                    elif isinstance(block, dict) and "text" in block:
                        text_parts.append(str(block["text"]))
                return "\n".join(text_parts)

            # If content has a text attribute
            if hasattr(content, "text"):
                return str(content.text)

            # If content is a dict with text
            if isinstance(content, dict) and "text" in content:
                return str(content["text"])

            # Fallback: convert to string and try to parse
            content_str = str(content)
            if "TextBlock" in content_str:
                import re

                # Extract text from TextBlock patterns
                text_pattern = r"text='([^']*(?:\\'[^']*)*)'"
                matches = re.findall(text_pattern, content_str, re.DOTALL)
                if matches:
                    # Join all text matches and unescape
                    text = "\n".join(matches)
                    return (
                        text.replace("\\'", "'")
                        .replace("\\n", "\n")
                        .replace("\\\\", "\\")
                    )

            return content_str

        except Exception as e:
            logger.warning(f"Failed to extract text from message content: {e}")
            return str(content)

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

            # Enhance with cidx tool capability
            prompt += """

ADDITIONAL SEMANTIC SEARCH CAPABILITY:
This codebase includes a built-in semantic search tool accessible via Bash:
- `cidx query "search terms"` - Find semantically similar code
- `cidx query "search terms" --limit 5` - Limit results  
- `cidx query "search terms" --language python` - Filter by language
- `cidx --help` - See all available commands

Use this when you need to find related code that might not be in the initial context."""

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

            # Enhance with cidx tool capability
            prompt += """

ADDITIONAL SEMANTIC SEARCH CAPABILITY:
This codebase includes a built-in semantic search tool accessible via Bash:
- `cidx query "search terms"` - Find semantically similar code
- `cidx query "search terms" --limit 5` - Limit results  
- `cidx query "search terms" --language python` - Filter by language
- `cidx --help` - See all available commands

Use this when you need to find related code that might not be in the initial context."""

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

    async def stream_analysis(
        self,
        user_query: str,
        search_results: List[Dict[str, Any]],
        context_lines: int = 500,
        max_turns: int = 5,
        project_info: Optional[Dict[str, Any]] = None,
        enable_exploration: bool = True,
        claude_options: Optional[ClaudeCodeOptions] = None,
    ) -> AsyncIterator[str]:
        """Stream Claude analysis results as they arrive.

        Args:
            user_query: The user's question
            search_results: Results from semantic search
            context_lines: Lines of context around each match
            max_turns: Maximum conversation turns
            project_info: Project metadata
            enable_exploration: Whether to enable file exploration
            claude_options: Custom Claude options

        Yields:
            String chunks of the analysis response
        """
        try:
            # Extract contexts from search results
            # Ensure all file references are included by adjusting context size if needed
            contexts = self.context_extractor.extract_context_from_results(
                search_results,
                context_lines=context_lines,
                ensure_all_files=True,  # Prioritize including all files over context size
            )

            # Create analysis prompt
            prompt = self.create_analysis_prompt(
                user_query=user_query,
                contexts=contexts,
                project_info=project_info,
                enable_exploration=enable_exploration,
            )

            # TEMPORARY: Use simple prompt to avoid JSON issues
            prompt = f"You are a code analyst. Answer this question about the codebase: {user_query}\n\nProvided context:\n{self.context_extractor.format_contexts_for_prompt(contexts, include_line_numbers=True, max_context_length=10000) if contexts else 'No specific context found.'}"

            # Configure Claude options
            if claude_options is None:
                claude_options = ClaudeCodeOptions(
                    max_turns=1,
                    cwd=str(self.codebase_dir),
                    system_prompt="You are a code analyst. Analyze the code and answer the question.",
                )

            # Stream Claude responses
            logger.info(
                f"Starting Claude streaming analysis for query: {user_query[:100]}..."
            )

            async for message in query(prompt=prompt, options=claude_options):
                if hasattr(message, "content") and message.content:
                    # Extract text content from Claude SDK message
                    text_content = self._extract_text_from_message(message.content)
                    if text_content:
                        yield text_content

        except Exception as e:
            logger.error(f"Claude streaming analysis failed: {e}")
            yield f"Error during analysis: {str(e)}"

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
    """Check if Claude Code SDK is available."""
    return CLAUDE_SDK_AVAILABLE

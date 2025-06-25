"""
Claude tool usage tracking for real-time feedback and plan summaries.

This module provides classes to track Claude's tool usage during streaming analysis,
display real-time status updates, and generate comprehensive summaries of Claude's
problem-solving approach.
"""

import re
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from rich.console import Console


@dataclass
class ToolUsageEvent:
    """Represents a single tool usage event during Claude analysis."""

    tool_name: str  # "Bash", "Read", "Write", "Grep", etc.
    operation_type: str  # "cidx_semantic_search", "grep_search", "file_operation", etc.
    visual_cue: str  # "🔍✨", "😞", "📄", "⚡"
    target: str  # file path, search query, command target
    command_detail: str  # full command or operation details
    timestamp: datetime
    status: str  # "started", "completed", "failed"
    tool_use_id: Optional[str] = None
    duration: Optional[float] = None
    error_message: Optional[str] = None


class CommandClassifier:
    """Classifies bash commands to determine tool usage patterns and visual cues."""

    def classify_bash_command(self, command: str) -> Dict[str, Any]:
        """
        Classify a bash command and return classification details.

        Args:
            command: The bash command string to classify

        Returns:
            Dictionary with type, visual_cue, priority, and command_summary
        """
        command_lower = command.lower().strip()

        # cidx usage detection (our preferred semantic search)
        if command_lower.startswith("cidx ") or " cidx " in command_lower:
            return {
                "type": "cidx_semantic_search",
                "visual_cue": "🔍✨",  # Sparkly search for semantic search
                "priority": "high",
                "command_summary": self._extract_cidx_operation(command),
            }

        # grep usage detection (discouraged pattern)
        elif any(grep_cmd in command_lower for grep_cmd in ["grep ", "rg ", "ripgrep"]):
            return {
                "type": "grep_search",
                "visual_cue": "😞",  # Sad face for text-based search
                "priority": "medium",
                "command_summary": self._extract_grep_operation(command),
            }

        # Regular file operations
        elif any(
            cmd in command_lower for cmd in ["cat ", "head ", "tail ", "ls ", "find "]
        ):
            return {
                "type": "file_operation",
                "visual_cue": "📄",
                "priority": "low",
                "command_summary": self._extract_file_operation(command),
            }

        # Git operations
        elif command_lower.startswith("git "):
            return {
                "type": "git_operation",
                "visual_cue": "🌿",
                "priority": "medium",
                "command_summary": f"Git: {command}",
            }

        # Other bash commands
        else:
            return {
                "type": "bash_command",
                "visual_cue": "⚡",
                "priority": "low",
                "command_summary": f"Bash: {command}",
            }

    def _extract_cidx_operation(self, command: str) -> str:
        """Extract meaningful description from cidx command."""
        # Parse common cidx patterns
        if "cidx query" in command:
            # Extract the search term and any additional parameters
            match = re.search(r'cidx query [\'"]([^\'"]+)[\'"](.*)$', command)
            if match:
                query = match.group(1)
                additional_params = match.group(2).strip()
                if additional_params:
                    return f"Semantic search: '{query}' {additional_params}"
                else:
                    return f"Semantic search: '{query}'"
            else:
                # Try without quotes - capture everything after 'cidx query'
                match = re.search(r"cidx query (.+)$", command)
                if match:
                    query_and_params = match.group(1).strip()
                    # Check if there are additional parameters after the first word/phrase
                    parts = query_and_params.split()
                    if len(parts) > 1 and any(
                        part.startswith("--") for part in parts[1:]
                    ):
                        query = parts[0]
                        params = " ".join(parts[1:])
                        return f"Semantic search: '{query}' {params}"
                    else:
                        return f"Semantic search: '{query_and_params}'"
                else:
                    return "Semantic search"

        elif "cidx status" in command:
            return "Checking index status"

        elif "cidx index" in command:
            return "Indexing codebase"

        else:
            return f"cidx: {command[5:]}"  # After 'cidx '

    def _extract_grep_operation(self, command: str) -> str:
        """Extract meaningful description from grep command."""
        # Extract pattern from various grep formats
        patterns = [
            r'grep.*?[\'"]([^\'"]+)[\'"]',  # quoted pattern
            r"grep.*?(\w+)",  # simple word pattern
            r'rg.*?[\'"]([^\'"]+)[\'"]',  # ripgrep quoted
            r"rg.*?(\w+)",  # ripgrep simple
        ]

        for pattern in patterns:
            match = re.search(pattern, command)
            if match:
                search_term = match.group(1)
                return f"Text search: '{search_term}'"

        return f"Text search: {command}"

    def _extract_file_operation(self, command: str) -> str:
        """Extract meaningful description from file operation command."""
        command_parts = command.split()
        if not command_parts:
            return "File operation"

        cmd = command_parts[0]

        if cmd == "cat":
            if len(command_parts) > 1:
                return f"Reading: {command_parts[1]}"
            return "Reading file"

        elif cmd == "ls":
            if len(command_parts) > 1:
                return f"Listing: {command_parts[-1]}"
            return "Listing directory"

        elif cmd in ["head", "tail"]:
            if len(command_parts) > 1:
                return f"{cmd.title()}: {command_parts[-1]}"
            return f"{cmd.title()} of file"

        elif cmd == "find":
            return f"Finding files: {command[5:]}"

        else:
            return f"File ops: {command}"


class ToolUsageTracker:
    """Tracks tool usage events throughout a Claude analysis session."""

    def __init__(self) -> None:
        """Initialize the tool usage tracker."""
        self.events: List[ToolUsageEvent] = []
        self.active_events: Dict[str, ToolUsageEvent] = {}  # tool_use_id -> event
        self.start_time = datetime.now()

    def track_tool_start(self, event: ToolUsageEvent) -> None:
        """Record the start of a tool usage event."""
        self.events.append(event)
        if event.tool_use_id:
            self.active_events[event.tool_use_id] = event

    def track_tool_completion(self, tool_result_data: Dict[str, Any]) -> None:
        """Record the completion of a tool usage event."""
        tool_use_id = tool_result_data.get("tool_use_id")
        if not tool_use_id or tool_use_id not in self.active_events:
            return

        event = self.active_events[tool_use_id]
        completion_time = datetime.now()

        # Calculate duration
        duration = (completion_time - event.timestamp).total_seconds()
        event.duration = duration

        # Update status based on result
        is_error = tool_result_data.get("is_error", False)
        if is_error:
            event.status = "failed"
            event.error_message = str(tool_result_data.get("content", "Unknown error"))
        else:
            event.status = "completed"

        # Remove from active events
        del self.active_events[tool_use_id]

    def get_current_activity(self) -> Optional[str]:
        """Get a description of the current tool activity."""
        if not self.active_events:
            return None

        # Get the most recent active event
        latest_event = max(self.active_events.values(), key=lambda e: e.timestamp)
        return f"{latest_event.visual_cue} {latest_event.command_detail}"

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics of all tool usage."""
        if not self.events:
            return {
                "total_events": 0,
                "session_duration": 0,
                "tools_used": [],
                "operation_counts": {},
                "cidx_usage_count": 0,
                "grep_usage_count": 0,
                "average_tool_duration": 0,
            }

        # Calculate basic stats
        total_events = len(self.events)
        session_duration = (datetime.now() - self.start_time).total_seconds()

        # Count operations by type
        operation_counts: Dict[str, int] = {}
        tools_used = set()
        completed_events = [e for e in self.events if e.duration is not None]

        for event in self.events:
            tools_used.add(event.tool_name)
            operation_counts[event.operation_type] = (
                operation_counts.get(event.operation_type, 0) + 1
            )

        # Special counts for cidx vs grep
        cidx_usage_count = operation_counts.get("cidx_semantic_search", 0)
        grep_usage_count = operation_counts.get("grep_search", 0)

        # Average duration for completed events
        average_duration = 0.0
        if completed_events:
            average_duration = sum(
                e.duration for e in completed_events if e.duration is not None
            ) / len(completed_events)

        return {
            "total_events": total_events,
            "session_duration": session_duration,
            "tools_used": list(tools_used),
            "operation_counts": operation_counts,
            "cidx_usage_count": cidx_usage_count,
            "grep_usage_count": grep_usage_count,
            "average_tool_duration": average_duration,
            "completed_events": len(completed_events),
            "failed_events": len([e for e in self.events if e.status == "failed"]),
            "active_events": len(self.active_events),
        }

    def get_all_events(self) -> List[ToolUsageEvent]:
        """Get all recorded tool usage events."""
        return self.events.copy()


class StatusLineManager:
    """Manages the real-time status line display during Claude analysis using common framework."""

    def __init__(
        self, console: Optional[Console] = None, use_split_display: bool = False
    ) -> None:
        """Initialize the status line manager."""
        from ..utils.status_display import (
            StatusDisplayManager,
            StatusDisplayMode,
            VisualCues,
        )

        # Choose display mode based on requirements
        if use_split_display:
            # Use TEXTUAL_STREAM for proper 3-region display
            # We'll capture Claude CLI output and route it through Textual instead of mixing modes
            display_mode = StatusDisplayMode.FREE_SCROLL_STREAM
        else:
            display_mode = StatusDisplayMode.ACTIVITY_LOG

        self.status_manager = StatusDisplayManager(
            mode=display_mode,
            console=console,
            handle_interrupts=False,  # Let parent handle interrupts
        )
        self.cidx_usage_count = 0
        self.grep_usage_count = 0
        self.visual_cues = VisualCues
        self.use_split_display = use_split_display
        self.session_start_time = datetime.now()

    def start_display(self) -> None:
        """Start the status line display."""
        self.session_start_time = datetime.now()
        self.status_manager.start("Claude analysis")

        # Initialize status bar
        if self.use_split_display:
            self._update_status_bar()

    def stop_display(self) -> None:
        """Stop the status line display."""
        self.status_manager.stop()

    def update_content(self, text: str) -> None:
        """Update main content area (for split displays)."""
        if self.use_split_display and hasattr(self.status_manager, "update_content"):
            # TEXTUAL_STREAM mode supports content updates through proper framework
            self.status_manager.update_content(text)
        # For non-split displays, content is handled by the caller

    def show_final_summary(self, summary_text: str) -> None:
        """Show final summary and transition from streaming to final view."""
        if self.use_split_display and hasattr(
            self.status_manager, "show_final_summary"
        ):
            # Use the display manager's final summary method for split displays
            self.status_manager.show_final_summary(summary_text)
        else:
            # Use regular summary formatting for non-split displays
            try:
                # Try to format summary, fallback to simple print if needed
                if hasattr(self.status_manager, "format_summary"):
                    self.status_manager.format_summary(
                        summary_text, title="Claude's Problem-Solving Approach"
                    )
                else:
                    # Fallback: print summary directly to console
                    if self.status_manager.console:
                        self.status_manager.console.print(
                            "\n🤖 Claude's Problem-Solving Approach"
                        )
                        self.status_manager.console.print("─" * 60)

                        # Split summary into narrative and statistics sections
                        lines = summary_text.split("\n")
                        in_stats_section = False

                        for line in lines:
                            stripped_line = line.strip()

                            # Check if we're entering the statistics section
                            if "📊 Tool Usage Statistics" in stripped_line:
                                in_stats_section = True
                                self.status_manager.console.print(
                                    "\n" + stripped_line, style="bold cyan"
                                )
                                continue

                            # Handle statistics section specially
                            if in_stats_section and stripped_line:
                                if "Operation Breakdown:" in stripped_line:
                                    self.status_manager.console.print(
                                        "\n" + stripped_line, style="bold"
                                    )
                                elif any(
                                    emoji in stripped_line
                                    for emoji in ["🔍✨", "😞", "📄"]
                                ):
                                    # Operation breakdown items
                                    self.status_manager.console.print(
                                        "  " + stripped_line
                                    )
                                elif stripped_line and not stripped_line.startswith(
                                    "##"
                                ):
                                    # Regular statistics lines
                                    self.status_manager.console.print(
                                        "  " + stripped_line
                                    )
                                else:
                                    self.status_manager.console.print("")
                            elif stripped_line:
                                # Regular narrative content
                                self.status_manager.console.print(line)
                            else:
                                self.status_manager.console.print("")
            except Exception:
                # Last resort: print to regular console
                from rich.console import Console

                console = Console()
                console.print("\n🤖 Claude's Problem-Solving Approach")
                console.print("─" * 60)

                # Split and format each line separately
                lines = summary_text.split("\n")
                in_stats_section = False

                for line in lines:
                    stripped_line = line.strip()

                    if "📊 Tool Usage Statistics" in stripped_line:
                        in_stats_section = True
                        console.print("\n" + stripped_line, style="bold cyan")
                        continue

                    if in_stats_section and stripped_line:
                        if "Operation Breakdown:" in stripped_line:
                            console.print("\n" + stripped_line, style="bold")
                        elif any(
                            emoji in stripped_line for emoji in ["🔍✨", "😞", "📄"]
                        ):
                            console.print("  " + stripped_line)
                        elif stripped_line and not stripped_line.startswith("##"):
                            console.print("  " + stripped_line)
                        else:
                            console.print("")
                    elif stripped_line:
                        console.print(line)
                    else:
                        console.print("")

    def update_activity(self, event: ToolUsageEvent) -> None:
        """Update the status line with a new tool activity."""
        # Count special tool usage
        if event.operation_type == "cidx_semantic_search":
            self.cidx_usage_count += 1
        elif event.operation_type == "grep_search":
            self.grep_usage_count += 1

        # Format the activity text and visual cue
        activity_text, visual_cue = self._format_activity_display(event)

        # Calculate appropriate truncation width for status panel
        try:
            import shutil

            terminal_width = shutil.get_terminal_size().columns
            # Reserve space for visual cue, borders, padding
            truncate_width = max(30, terminal_width - 15)
        except (OSError, AttributeError, ImportError):
            truncate_width = 60  # Safe fallback

        # Update using common framework with smart truncation
        self.status_manager.update(
            message=activity_text,
            visual_cue=visual_cue,
            style="dim",
            event_type="tool_activity",  # Mark as tool activity for split display
            truncate_width=truncate_width,
            operation_type=event.operation_type,  # Pass operation type for statistics
        )

        # Auto-update status bar with elapsed time and stats
        self._update_status_bar()

    def _format_activity_display(self, event: ToolUsageEvent) -> Tuple[str, str]:
        """Format a single tool event for display, returning (message, visual_cue)."""
        visual_cue = event.visual_cue

        # Special formatting for different operation types
        if event.operation_type == "cidx_semantic_search":
            return event.command_detail, self.visual_cues.SEMANTIC_SEARCH
        elif event.operation_type == "grep_search":
            return event.command_detail, self.visual_cues.TEXT_SEARCH
        elif event.tool_name == "Read":
            # File paths will be truncated by display framework
            return f"Reading: {event.target}", self.visual_cues.FILE_READ
        elif event.tool_name == "Write":
            # File paths will be truncated by display framework
            return f"Writing: {event.target}", self.visual_cues.FILE_WRITE
        else:
            return event.command_detail, visual_cue

    def update_status_info(self, info_lines: List[str]) -> None:
        """Update the dynamic status info band.

        Args:
            info_lines: List of strings to display in the status band.
                       Examples: running clock, progress info, stats, etc.
        """
        if self.use_split_display and hasattr(
            self.status_manager, "update_status_info"
        ):
            # TEXTUAL_STREAM mode supports status info updates through Textual framework
            self.status_manager.update_status_info(info_lines)

    def get_session_elapsed_time(self) -> float:
        """Get elapsed time since session start in seconds."""
        return (datetime.now() - self.session_start_time).total_seconds()

    def get_tool_usage_stats(self) -> Dict[str, int]:
        """Get current tool usage statistics."""
        return {
            "cidx_count": self.cidx_usage_count,
            "grep_count": self.grep_usage_count,
            "total_count": self.cidx_usage_count + self.grep_usage_count,
        }

    def _update_status_bar(self) -> None:
        """Update the persistent status bar with elapsed time and tool stats."""
        if not self.use_split_display:
            return

        # Throttle status updates to avoid spam
        current_time = datetime.now()
        if hasattr(self, "_last_status_update"):
            time_since_last = (current_time - self._last_status_update).total_seconds()
            if time_since_last < 2.0:  # Don't update more than every 2 seconds
                return
        self._last_status_update: datetime = current_time

        # Calculate elapsed time
        elapsed = self.get_session_elapsed_time()
        elapsed_str = self._format_elapsed_time(elapsed)

        # Get tool usage stats
        stats = self.get_tool_usage_stats()

        # Format status line
        status_line = f"⏱️ Query running: {elapsed_str} | Tools used: cidx({stats['cidx_count']}) grep({stats['grep_count']})"

        # Add second line with more details if there are tools used
        if stats["total_count"] > 0:
            status_lines = [
                status_line,
                f"📊 Total operations: {stats['total_count']} | Performance tracking active",
            ]
        else:
            status_lines = [status_line]

        # Update status info
        self.update_status_info(status_lines)

    def _format_elapsed_time(self, seconds: float) -> str:
        """Format elapsed time in a human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"


class ClaudePlanSummary:
    """Generates comprehensive summaries of Claude's problem-solving approach."""

    def __init__(self) -> None:
        """Initialize the plan summary generator."""
        pass

    def generate_narrative(self, events: List[ToolUsageEvent]) -> str:
        """Generate a narrative description of Claude's problem-solving approach."""
        if not events:
            return "No tool usage recorded during analysis."

        # Categorize events by strategy
        categories = self._categorize_search_strategies(events)

        narrative_parts = []

        # Opening summary
        narrative_parts.append(f"Claude used {len(events)} tools during analysis:")
        narrative_parts.append("")  # Add blank line after opening

        # Search strategy analysis
        if categories["semantic_search"]:
            cidx_count = len(categories["semantic_search"])
            narrative_parts.append(
                f"- ✅ **Preferred Approach**: Used semantic search ({cidx_count}x) with `cidx` for intelligent code discovery"
            )

            # Show examples of semantic searches
            for event in categories["semantic_search"][:3]:  # Show first 3
                narrative_parts.append(f"  - {event.command_detail}")

            # Add spacing after examples
            if categories["semantic_search"]:
                narrative_parts.append("")

        if categories["text_search"]:
            grep_count = len(categories["text_search"])
            narrative_parts.append(
                f"- ⚠️ **Text-Based Search**: Used grep/text search ({grep_count}x) - consider using `cidx` for better semantic results"
            )
            narrative_parts.append("")

        # File exploration
        if categories["file_operations"]:
            file_count = len(categories["file_operations"])
            narrative_parts.append(
                f"- 📖 **Code Exploration**: Accessed {file_count} files for detailed analysis"
            )
            narrative_parts.append("")

        # Performance insights
        completed_events = [e for e in events if e.duration is not None]
        if completed_events:
            avg_duration = sum(
                e.duration for e in completed_events if e.duration is not None
            ) / len(completed_events)
            narrative_parts.append(
                f"- ⏱️ **Performance**: Average tool execution time {avg_duration:.2f}s"
            )

        return "\n".join(narrative_parts)

    def format_statistics(self, events: List[ToolUsageEvent]) -> str:
        """Format detailed statistics about tool usage."""
        if not events:
            return "No statistics available."

        stats_parts = []

        # Basic counts
        operation_counts: Dict[str, int] = {}
        tools_used = set()
        total_duration = 0.0
        completed_count = 0

        for event in events:
            operation_counts[event.operation_type] = (
                operation_counts.get(event.operation_type, 0) + 1
            )
            tools_used.add(event.tool_name)
            if event.duration:
                total_duration += event.duration
                completed_count += 1

        # Use simpler formatting that looks good in plain text
        stats_parts.append("📊 Tool Usage Statistics")
        stats_parts.append("")
        stats_parts.append(f"• Total Operations: {len(events)}")
        stats_parts.append(f"• Tools Used: {', '.join(sorted(tools_used))}")
        stats_parts.append(f"• Completed Successfully: {completed_count}")

        if total_duration > 0:
            stats_parts.append(f"• Total Execution Time: {total_duration:.2f}s")
            stats_parts.append(
                f"• Average Duration: {total_duration/completed_count:.2f}s"
            )

        # Operation breakdown with cleaner formatting
        if operation_counts:
            stats_parts.append("")
            stats_parts.append("Operation Breakdown:")
            for op_type, count in sorted(operation_counts.items()):
                emoji = (
                    "🔍✨"
                    if op_type == "cidx_semantic_search"
                    else "😞" if op_type == "grep_search" else "📄"
                )
                stats_parts.append(f"  {emoji} {op_type}: {count}")

        return "\n".join(stats_parts)

    def generate_complete_summary(self, events: List[ToolUsageEvent]) -> str:
        """Generate a complete summary including narrative and statistics."""
        if not events:
            return "No tool usage data available for analysis."

        narrative = self.generate_narrative(events)
        statistics = self.format_statistics(events)

        return f"{narrative}\n\n{statistics}"

    def _analyze_tool_patterns(self, events: List[ToolUsageEvent]) -> Dict[str, Any]:
        """Analyze patterns in tool usage for insights."""
        patterns = {
            "starts_with_semantic": False,
            "heavy_file_exploration": False,
            "grep_after_cidx": False,
            "sequential_reads": 0,
        }

        if not events:
            return patterns

        # Check if starts with semantic search
        if events[0].operation_type == "cidx_semantic_search":
            patterns["starts_with_semantic"] = True

        # Check for heavy file exploration
        file_ops = [e for e in events if e.operation_type == "file_operation"]
        if len(file_ops) > 5:
            patterns["heavy_file_exploration"] = True

        # Check for grep after cidx (potentially inefficient pattern)
        for i in range(len(events) - 1):
            if (
                events[i].operation_type == "cidx_semantic_search"
                and events[i + 1].operation_type == "grep_search"
            ):
                patterns["grep_after_cidx"] = True
                break

        # Count sequential read operations
        read_sequence = 0
        max_read_sequence = 0
        for event in events:
            if event.tool_name == "Read":
                read_sequence += 1
                max_read_sequence = max(max_read_sequence, read_sequence)
            else:
                read_sequence = 0
        patterns["sequential_reads"] = max_read_sequence

        return patterns

    def _categorize_search_strategies(
        self, events: List[ToolUsageEvent]
    ) -> Dict[str, List[ToolUsageEvent]]:
        """Categorize events by search strategy (semantic vs text-based)."""
        categories: Dict[str, List[ToolUsageEvent]] = {
            "semantic_search": [],
            "text_search": [],
            "file_operations": [],
            "git_operations": [],
            "other": [],
        }

        for event in events:
            if event.operation_type == "cidx_semantic_search":
                categories["semantic_search"].append(event)
            elif event.operation_type == "grep_search":
                categories["text_search"].append(event)
            elif event.operation_type == "file_operation":
                categories["file_operations"].append(event)
            elif event.operation_type == "git_operation":
                categories["git_operations"].append(event)
            else:
                categories["other"].append(event)

        return categories


def process_tool_use_event(
    tool_data: Dict[str, Any], classifier: CommandClassifier
) -> ToolUsageEvent:
    """
    Process a tool_use JSON event from Claude CLI stream and create a ToolUsageEvent.

    Args:
        tool_data: The parsed JSON data from a tool_use event
        classifier: CommandClassifier instance for bash command analysis

    Returns:
        ToolUsageEvent instance representing the tool usage
    """
    tool_name = tool_data.get("name", "Unknown")
    tool_use_id = tool_data.get("id")  # Claude CLI uses "id" not "tool_use_id"
    tool_input = tool_data.get("input", {})

    def _format_parameters(
        params: Dict[str, Any], exclude_keys: Optional[List[str]] = None
    ) -> str:
        """Format tool parameters for display."""
        if not params:
            return ""

        exclude_keys = exclude_keys or []
        relevant_params = {k: v for k, v in params.items() if k not in exclude_keys}

        if not relevant_params:
            return ""

        # Format parameters as key=value pairs
        param_strs = []
        for key, value in relevant_params.items():
            # Truncate long values
            if isinstance(value, str) and len(value) > 50:
                value = value[:47] + "..."
            param_strs.append(f"{key}={value}")

        return f" ({', '.join(param_strs)})" if param_strs else ""

    # Handle different tool types
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        classification = classifier.classify_bash_command(command)
        params_str = _format_parameters(tool_input, exclude_keys=["command"])

        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type=classification["type"],
            visual_cue=classification["visual_cue"],
            target=command,  # Let display framework handle truncation
            command_detail=f"{classification['command_summary']}{params_str}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "unknown")
        params_str = _format_parameters(tool_input, exclude_keys=["file_path"])
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="file_operation",
            visual_cue="📖",
            target=file_path,
            command_detail=f"Reading: {file_path}{params_str}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "Write":
        file_path = tool_input.get("file_path", "unknown")
        params_str = _format_parameters(
            tool_input, exclude_keys=["file_path", "content"]
        )
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="file_operation",
            visual_cue="📝",
            target=file_path,
            command_detail=f"Writing: {file_path}{params_str}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "unknown")
        params_str = _format_parameters(tool_input, exclude_keys=["pattern"])
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="grep_search",
            visual_cue="😞",  # Sad face for text-based search
            target=pattern,
            command_detail=f"Text search: '{pattern}'{params_str}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "unknown")
        params_str = _format_parameters(tool_input, exclude_keys=["pattern"])
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="file_search",
            visual_cue="🔍",
            target=pattern,
            command_detail=f"File pattern: '{pattern}'{params_str}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "LS":
        path = tool_input.get("path", ".")
        params_str = _format_parameters(tool_input, exclude_keys=["path"])
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="file_operation",
            visual_cue="🗂️",
            target=path,
            command_detail=f"Listing: {path}{params_str}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    # Generic tool handling
    else:
        # Format tool input more intelligently
        if isinstance(tool_input, dict):
            # Extract meaningful info from tool input
            if "description" in tool_input:
                target = tool_input["description"]
                params_str = _format_parameters(
                    tool_input, exclude_keys=["description"]
                )
                detail = f"{tool_name}: {tool_input['description']}{params_str}"
            elif "path" in tool_input:
                target = tool_input["path"]
                params_str = _format_parameters(tool_input, exclude_keys=["path"])
                detail = f"{tool_name}: {tool_input['path']}{params_str}"
            elif "pattern" in tool_input:
                target = tool_input["pattern"]
                params_str = _format_parameters(tool_input, exclude_keys=["pattern"])
                detail = f"{tool_name}: {tool_input['pattern']}{params_str}"
            else:
                # Get the first key-value pair that looks meaningful
                first_key = next(iter(tool_input.keys())) if tool_input else "unknown"
                first_value = tool_input.get(first_key, "unknown")
                target = str(first_value)
                params_str = _format_parameters(tool_input, exclude_keys=[first_key])
                detail = f"{tool_name}: {first_key}={str(first_value)}{params_str}"
        else:
            target = str(tool_input)
            detail = f"{tool_name}: {str(tool_input)}"

        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="tool_operation",
            visual_cue="🔧",
            target=target,
            command_detail=detail,
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

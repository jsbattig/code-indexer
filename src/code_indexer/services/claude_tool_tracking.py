"""
Claude tool usage tracking for real-time feedback and plan summaries.

This module provides classes to track Claude's tool usage during streaming analysis,
display real-time status updates, and generate comprehensive summaries of Claude's
problem-solving approach.
"""

import re
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from rich.console import Console
from rich.live import Live
from rich.text import Text


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
                "command_summary": f"Git: {command[:40]}...",
            }

        # Other bash commands
        else:
            return {
                "type": "bash_command",
                "visual_cue": "⚡",
                "priority": "low",
                "command_summary": f"Bash: {command[:30]}...",
            }

    def _extract_cidx_operation(self, command: str) -> str:
        """Extract meaningful description from cidx command."""
        # Parse common cidx patterns
        if "cidx query" in command:
            # Extract the search term using regex
            match = re.search(r'cidx query [\'"]([^\'"]+)[\'"]', command)
            if match:
                query = match.group(1)
                return f"Semantic search: '{query}'"
            else:
                # Try without quotes
                match = re.search(r"cidx query ([^\s]+)", command)
                if match:
                    query = match.group(1)
                    return f"Semantic search: '{query}'"
                else:
                    return "Semantic search"

        elif "cidx status" in command:
            return "Checking index status"

        elif "cidx index" in command:
            return "Indexing codebase"

        else:
            return f"cidx: {command[5:35]}..."  # First 30 chars after 'cidx '

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

        return f"Text search: {command[:30]}..."

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
            return f"Finding files: {command[5:30]}..."

        else:
            return f"File ops: {command[:25]}..."


class ToolUsageTracker:
    """Tracks tool usage events throughout a Claude analysis session."""

    def __init__(self):
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
    """Manages the real-time status line display during Claude analysis."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize the status line manager."""
        self.console = console or Console()
        self.live_display: Optional[Live] = None
        self.current_activities: List[str] = []
        self.cidx_usage_count = 0
        self.grep_usage_count = 0
        self.max_activities = 3  # Show up to 3 recent activities

    def start_display(self) -> None:
        """Start the live status line display."""
        if not self.live_display:
            self.live_display = Live(
                Text("🤖 Claude analysis starting..."),
                console=self.console,
                auto_refresh=True,
                refresh_per_second=2,
            )
            self.live_display.start()

    def stop_display(self) -> None:
        """Stop the live status line display."""
        if self.live_display:
            self.live_display.stop()
            self.live_display = None

    def update_activity(self, event: ToolUsageEvent) -> None:
        """Update the status line with a new tool activity."""
        # Count special tool usage
        if event.operation_type == "cidx_semantic_search":
            self.cidx_usage_count += 1
        elif event.operation_type == "grep_search":
            self.grep_usage_count += 1

        # Format the activity text
        activity_text = self._format_activity_text(event)

        # Add to activities list and keep only recent ones
        self.current_activities.append(activity_text)
        if len(self.current_activities) > self.max_activities:
            self.current_activities.pop(0)

        # Update the live display
        if self.live_display:
            status_display = self._create_status_display()
            self.live_display.update(status_display)

    def _format_activity_text(self, event: ToolUsageEvent) -> str:
        """Format a single tool event for display."""
        # Special formatting for different operation types
        if event.operation_type == "cidx_semantic_search":
            return f"{event.visual_cue} {event.command_detail}"
        elif event.operation_type == "grep_search":
            return f"{event.visual_cue} {event.command_detail}"
        elif event.tool_name == "Read":
            # Shorten file paths for display
            file_path = event.target
            if len(file_path) > 30:
                file_path = "..." + file_path[-27:]
            return f"{event.visual_cue} Reading: {file_path}"
        elif event.tool_name == "Write":
            file_path = event.target
            if len(file_path) > 30:
                file_path = "..." + file_path[-27:]
            return f"{event.visual_cue} Writing: {file_path}"
        else:
            return f"{event.visual_cue} {event.command_detail}"

    def _create_status_display(self) -> Text:
        """Create the complete status display."""
        text = Text()

        # Add current activities
        if self.current_activities:
            activities_text = " • ".join(self.current_activities)
            text.append(activities_text)
        else:
            text.append("🤖 Analyzing...")

        # Add usage counters if any
        if self.cidx_usage_count > 0 or self.grep_usage_count > 0:
            counters = []
            if self.cidx_usage_count > 0:
                counters.append(f"🔍✨ {self.cidx_usage_count}")
            if self.grep_usage_count > 0:
                counters.append(f"😞 {self.grep_usage_count}")

            text.append(" | ")
            text.append(" ".join(counters), style="dim")

        return text

    def _format_status_line(self, event: ToolUsageEvent) -> Text:
        """Format a single tool event for status line display."""
        text = Text()
        text.append(event.visual_cue + " ")
        text.append(event.command_detail)
        return text

    def _render_status_line(self, status_text: str) -> None:
        """Render the status line with given text."""
        if self.live_display:
            self.live_display.update(Text(status_text))


class ClaudePlanSummary:
    """Generates comprehensive summaries of Claude's problem-solving approach."""

    def __init__(self):
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

        # Search strategy analysis
        if categories["semantic_search"]:
            cidx_count = len(categories["semantic_search"])
            narrative_parts.append(
                f"✅ **Preferred Approach**: Used semantic search ({cidx_count}x) with `cidx` for intelligent code discovery"
            )

            # Show examples of semantic searches
            for event in categories["semantic_search"][:3]:  # Show first 3
                narrative_parts.append(f"   • {event.command_detail}")

        if categories["text_search"]:
            grep_count = len(categories["text_search"])
            narrative_parts.append(
                f"⚠️ **Text-Based Search**: Used grep/text search ({grep_count}x) - consider using `cidx` for better semantic results"
            )

        # File exploration
        if categories["file_operations"]:
            file_count = len(categories["file_operations"])
            narrative_parts.append(
                f"📖 **Code Exploration**: Accessed {file_count} files for detailed analysis"
            )

        # Performance insights
        completed_events = [e for e in events if e.duration is not None]
        if completed_events:
            avg_duration = sum(
                e.duration for e in completed_events if e.duration is not None
            ) / len(completed_events)
            narrative_parts.append(
                f"⏱️ **Performance**: Average tool execution time {avg_duration:.2f}s"
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

        stats_parts.append("## 📊 Tool Usage Statistics")
        stats_parts.append(f"• **Total Operations**: {len(events)}")
        stats_parts.append(f"• **Tools Used**: {', '.join(sorted(tools_used))}")
        stats_parts.append(f"• **Completed Successfully**: {completed_count}")

        if total_duration > 0:
            stats_parts.append(f"• **Total Execution Time**: {total_duration:.2f}s")
            stats_parts.append(
                f"• **Average Duration**: {total_duration/completed_count:.2f}s"
            )

        # Operation breakdown
        if operation_counts:
            stats_parts.append("\n**Operation Breakdown**:")
            for op_type, count in sorted(operation_counts.items()):
                emoji = (
                    "🔍✨"
                    if op_type == "cidx_semantic_search"
                    else "😞" if op_type == "grep_search" else "📄"
                )
                stats_parts.append(f"• {emoji} {op_type}: {count}")

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
    tool_use_id = tool_data.get("tool_use_id")
    tool_input = tool_data.get("input", {})

    # Handle different tool types
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        classification = classifier.classify_bash_command(command)

        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type=classification["type"],
            visual_cue=classification["visual_cue"],
            target=command[:50] + "..." if len(command) > 50 else command,
            command_detail=classification["command_summary"],
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "unknown")
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="file_operation",
            visual_cue="📖",
            target=file_path,
            command_detail=f"Reading: {file_path}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "Write":
        file_path = tool_input.get("file_path", "unknown")
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="file_operation",
            visual_cue="📝",
            target=file_path,
            command_detail=f"Writing: {file_path}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "unknown")
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="grep_search",
            visual_cue="😞",  # Sad face for text-based search
            target=pattern,
            command_detail=f"Text search: '{pattern}'",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "unknown")
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="file_search",
            visual_cue="🔍",
            target=pattern,
            command_detail=f"File pattern: '{pattern}'",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    elif tool_name == "LS":
        path = tool_input.get("path", ".")
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="file_operation",
            visual_cue="🗂️",
            target=path,
            command_detail=f"Listing: {path}",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

    # Generic tool handling
    else:
        return ToolUsageEvent(
            tool_name=tool_name,
            operation_type="tool_operation",
            visual_cue="🔧",
            target=str(tool_input),
            command_detail=f"{tool_name}: {str(tool_input)[:40]}...",
            timestamp=datetime.now(),
            status="started",
            tool_use_id=tool_use_id,
        )

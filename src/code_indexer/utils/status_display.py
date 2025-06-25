"""
Common status display framework for code-indexer operations.

Provides unified status display patterns for:
- File watching operations
- Indexing operations
- Claude AI analysis
- Other long-running operations

Supports multiple display modes:
- Progress bars with metrics
- Real-time activity logging
- Status spinners
- Custom status messages
"""

import signal
import shutil
import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any, List, Union, Callable

from rich.console import Console
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    Column,
)
from rich.markdown import Markdown
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live

# Textual components removed - using Rich-only implementation


logger = logging.getLogger(__name__)


class StatusDisplayMode:
    """Status display mode constants."""

    PROGRESS_BAR = "progress_bar"
    ACTIVITY_LOG = "activity_log"
    SPINNER = "spinner"
    SILENT = "silent"
    SPLIT_STREAM = "split_stream"  # For Claude streaming with separate text/tool areas
    FREE_SCROLL_STREAM = "free_scroll_stream"  # Free scrolling content + fixed bottom status (Rich-based)


class StatusEvent:
    """Represents a status event with visual cues and details."""

    def __init__(
        self,
        message: str,
        visual_cue: str = "•",
        style: str = "dim",
        event_type: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
        truncate_width: Optional[int] = None,
    ):
        self.message = message
        self.visual_cue = visual_cue
        self.style = style
        self.event_type = event_type
        self.metadata = metadata or {}
        self.truncate_width = truncate_width
        self.timestamp = datetime.now()


class BaseStatusDisplay(ABC):
    """Base class for status display implementations."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.is_active = False
        self.start_time: Optional[datetime] = None

    @abstractmethod
    def start(self, operation_name: str) -> None:
        """Start the status display."""
        pass

    @abstractmethod
    def update(self, event: StatusEvent) -> None:
        """Update the status display with new event."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the status display."""
        pass

    def format_duration(self, start_time: datetime) -> str:
        """Format elapsed time since start."""
        duration = datetime.now() - start_time
        total_seconds = duration.total_seconds()

        if total_seconds < 60:
            return f"{total_seconds:.1f}s"
        elif total_seconds < 3600:
            minutes = int(total_seconds // 60)
            seconds = int(total_seconds % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def smart_truncate(
        self, text: str, max_width: Optional[int] = None, context: str = "default"
    ) -> str:
        """Smart truncation based on available width and context."""
        if max_width is None:
            try:
                terminal_width = shutil.get_terminal_size().columns
                max_width = max(40, terminal_width - 20)  # Leave space for formatting
            except (OSError, AttributeError):
                max_width = 60  # Safe fallback

        if len(text) <= max_width:
            return text

        # Smart truncation strategies based on context
        if context == "file_path" and "/" in text:
            # For file paths, prioritize filename
            parts = text.split("/")
            filename = parts[-1]
            if len(filename) <= max_width:
                return filename
            if len(parts) > 1 and len(filename) < max_width - 10:
                parent = parts[-2]
                candidate = f"{parent}/{filename}"
                if len(candidate) <= max_width:
                    return candidate
                # Show truncated path
                remaining = max_width - len(filename) - 4
                if remaining > 3:
                    return f".../{parent[:remaining]}/{filename}"
            return filename[: max_width - 3] + "..."

        elif context == "command" and " " in text:
            # For commands, try to keep command name and key arguments
            parts = text.split()
            if len(parts) > 1:
                cmd = parts[0]
                if len(cmd) < max_width - 10:
                    remaining = max_width - len(cmd) - 1
                    args = " ".join(parts[1:])
                    if len(args) <= remaining:
                        return text
                    return f"{cmd} {args[:remaining-3]}..."

        # Default truncation
        return text[: max_width - 3] + "..."


class ProgressBarDisplay(BaseStatusDisplay):
    """Progress bar status display for operations with measurable progress."""

    def __init__(
        self,
        console: Optional[Console] = None,
        show_time_remaining: bool = True,
        bar_width: int = 30,
    ):
        super().__init__(console)
        self.show_time_remaining = show_time_remaining
        self.bar_width = bar_width
        self.progress: Optional[Progress] = None
        self.task_id: Optional[int] = None

    def start(self, operation_name: str) -> None:
        """Start progress bar display."""
        if self.is_active:
            return

        self.is_active = True
        self.start_time = datetime.now()

        columns = [
            TextColumn(f"[bold blue]{operation_name}", justify="right"),
            BarColumn(bar_width=self.bar_width),
            TaskProgressColumn(),
            "•",
            TimeElapsedColumn(),
        ]

        if self.show_time_remaining:
            columns.extend(["•", TimeRemainingColumn()])

        columns.extend(
            [
                "•",
                TextColumn(
                    "[cyan]{task.description}",
                    table_column=Column(no_wrap=False, overflow="fold"),
                ),
            ]
        )

        self.progress = Progress(*columns, console=self.console)
        self.progress.start()
        self.task_id = self.progress.add_task("Starting...", total=100)

    def update(self, event: StatusEvent) -> None:
        """Update progress bar with new event."""
        if not self.is_active or not self.progress or self.task_id is None:
            return

        # Extract progress info from metadata
        completed = event.metadata.get("completed", 0)
        total = event.metadata.get("total", 100)
        description = event.message

        # Update progress
        if total > 0:
            progress_percent = (completed / total) * 100
            self.progress.update(
                self.task_id, completed=progress_percent, description=description
            )

    def stop(self) -> None:
        """Stop progress bar display."""
        if self.progress:
            self.progress.stop()
            self.progress = None
            self.task_id = None
        self.is_active = False


class ActivityLogDisplay(BaseStatusDisplay):
    """Real-time activity logging for streaming operations."""

    def __init__(self, console: Optional[Console] = None, max_recent_events: int = 5):
        super().__init__(console)
        self.max_recent_events = max_recent_events
        self.recent_events: List[StatusEvent] = []

    def start(self, operation_name: str) -> None:
        """Start activity logging."""
        if self.is_active:
            return

        self.is_active = True
        self.start_time = datetime.now()
        self.console.print(f"🤖 {operation_name} starting...", style="dim")

    def update(self, event: StatusEvent) -> None:
        """Log new activity event."""
        if not self.is_active:
            return

        # Add to recent events
        self.recent_events.append(event)
        if len(self.recent_events) > self.max_recent_events:
            self.recent_events.pop(0)

        # Print the event
        message = f"{event.visual_cue} {event.message}"
        self.console.print(message, style=event.style)

    def stop(self) -> None:
        """Stop activity logging."""
        self.is_active = False


class SpinnerDisplay(BaseStatusDisplay):
    """Spinner status display for indeterminate operations."""

    def __init__(self, console: Optional[Console] = None):
        super().__init__(console)
        self.status_context = None

    def start(self, operation_name: str) -> None:
        """Start spinner display."""
        if self.is_active:
            return

        self.is_active = True
        self.start_time = datetime.now()
        self.status_context = self.console.status(f"{operation_name}...")
        if self.status_context is not None:
            self.status_context.__enter__()

    def update(self, event: StatusEvent) -> None:
        """Update spinner message."""
        if not self.is_active or not self.status_context:
            return

        self.status_context.update(f"{event.message}...")

    def stop(self) -> None:
        """Stop spinner display."""
        if self.status_context:
            self.status_context.__exit__(None, None, None)
            self.status_context = None
        self.is_active = False


class SilentDisplay(BaseStatusDisplay):
    """Silent status display (no output)."""

    def start(self, operation_name: str) -> None:
        self.is_active = True
        self.start_time = datetime.now()

    def update(self, event: StatusEvent) -> None:
        pass

    def stop(self) -> None:
        self.is_active = False


class SplitStreamDisplay(BaseStatusDisplay):
    """Split display for streaming operations with separate text and tool areas."""

    def __init__(self, console: Optional[Console] = None, max_tool_lines: int = 3):
        super().__init__(console)
        self.max_tool_lines = max_tool_lines
        self.layout: Optional[Layout] = None
        self.live_display: Optional[Live] = None
        self.tool_activities: List[str] = []
        self.content_buffer: List[str] = []

    def start(self, operation_name: str) -> None:
        """Start split stream display with layout."""
        if self.is_active:
            return

        self.is_active = True
        self.start_time = datetime.now()

        # Create layout with main content area and tool status area
        self.layout = Layout()
        self.layout.split_column(
            Layout(name="main", ratio=4),  # Main content area (80%)
            Layout(
                name="tools", size=self.max_tool_lines + 2
            ),  # Tool area (fixed height)
        )

        # Initialize content
        self.layout["main"].update(
            Panel("", title=f"🤖 {operation_name}", border_style="blue")
        )
        self.layout["tools"].update(
            Panel("Ready...", title="Tool Activity", border_style="green")
        )

        # Start live display
        self.live_display = Live(
            self.layout, console=self.console, refresh_per_second=10
        )
        self.live_display.start()

    def update(self, event: StatusEvent) -> None:
        """Update display with new content or tool activity."""
        if not self.is_active or not self.layout:
            return

        # Check if this is tool activity or content
        if event.event_type == "tool_activity":
            self._update_tool_area(event)
        else:
            self._update_content_area(event)

    def update_content(self, text: str) -> None:
        """Update main content area with streaming text."""
        if not self.is_active or not self.layout:
            return

        # Add to buffer and update display
        self.content_buffer.append(text)

        # Keep buffer manageable (last 100 lines)
        if len(self.content_buffer) > 100:
            self.content_buffer.pop(0)

        # Update main panel with all content
        content_text = "".join(self.content_buffer)

        # Check if content contains markdown and render appropriately
        if self._has_markdown_patterns(content_text):
            try:
                processed_content = _process_markdown_for_readability(content_text)

                # Note: For Layout/Panel rendering, we use the processed markdown directly
                # Theme application would require console-level changes which are complex in layouts
                # The link processing will have already made links more readable
                rendered_content = Markdown(processed_content)
            except Exception:
                # Fall back to plain text if markdown rendering fails
                rendered_content = content_text
        else:
            rendered_content = content_text

        self.layout["main"].update(
            Panel(
                rendered_content,
                title="🤖 Claude Analysis Results",
                border_style="blue",
                height=None,  # Auto-size
            )
        )

    def _has_markdown_patterns(self, text: str) -> bool:
        """Check if text contains markdown patterns."""
        if not text or len(text.strip()) < 20:
            return False

        # Check for common markdown patterns
        lines = text.split("\n")
        markdown_indicators = [
            lambda line: line.strip().startswith("#"),  # Headers
            lambda line: line.strip().startswith("```"),  # Code blocks
            lambda line: line.strip().startswith("- ")
            or line.strip().startswith("* "),  # Lists
            lambda line: "**" in line or "__" in line,  # Bold
            lambda line: line.strip().startswith("> "),  # Quotes
            lambda line: "`" in line and line.count("`") >= 2,  # Inline code
        ]

        return any(
            any(indicator(line) for indicator in markdown_indicators)
            for line in lines[:10]  # Check first 10 lines
        )

    def _update_tool_area(self, event: StatusEvent) -> None:
        """Update tool activity area."""
        # Apply smart truncation if requested
        message = event.message
        if event.truncate_width:
            message = self.smart_truncate(message, event.truncate_width, "command")

        # Format tool activity
        activity_line = f"{event.visual_cue} {message}"

        # Add to activities and keep only recent ones
        self.tool_activities.append(activity_line)
        if len(self.tool_activities) > self.max_tool_lines:
            self.tool_activities.pop(0)

        # Update tool panel
        tool_text = "\n".join(self.tool_activities)
        if self.layout is not None:
            self.layout["tools"].update(
                Panel(
                    tool_text,
                    title="Tool Activity",
                    border_style="green",
                    height=self.max_tool_lines + 2,
                    expand=True,
                )
            )

    def _update_content_area(self, event: StatusEvent) -> None:
        """Update main content area with event."""
        content_line = f"{event.visual_cue} {event.message}\n"
        self.update_content(content_line)

    def stop(self) -> None:
        """Stop split stream display."""
        if self.live_display:
            self.live_display.stop()
            self.live_display = None
        self.layout = None
        self.is_active = False


class FreeScrollStreamDisplay(BaseStatusDisplay):
    """Free scrolling content with persistent bottom-pinned tool panel.

    Design philosophy:
    - Free scrolling content area (normal console output)
    - Single persistent tool panel pinned to bottom (like Claude Code)
    - Tool panel updates in place, content scrolls above it
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        max_status_lines: int = 3,
        max_info_lines: int = 2,
    ):
        super().__init__(console)
        self.max_status_lines = max_status_lines
        self.max_info_lines = max_info_lines
        self.tool_activities: List[str] = []
        self.status_info: List[str] = []
        self.live_display: Optional[Live] = None
        self.showing_tool_panel = False
        self.current_info_lines = 0
        self._last_status_lines = 0

    def start(self, operation_name: str) -> None:
        """Start free scroll display with clean interface."""
        if self.is_active:
            return

        self.is_active = True
        self.start_time = datetime.now()
        self.showing_tool_panel = False

        # Print initial header for content area (free scrolling)
        self.console.print(f"🤖 {operation_name}")
        self.console.print("─" * 80)

    def update(self, event: StatusEvent) -> None:
        """Update display with new content or tool activity."""
        if not self.is_active:
            return

        # Check if this is tool activity or content
        if event.event_type == "tool_activity":
            self._update_tool_activities(event)
        elif event.event_type == "status_info":
            self._update_status_info(event)
        else:
            # For content events, just print normally (free scrolling)
            self.console.print(f"{event.visual_cue} {event.message}")

    def update_content(self, text: str) -> None:
        """Update main content area with streaming text (free scrolling)."""
        if not self.is_active:
            return

        # Temporarily hide the panel to prevent content overlap
        panel_was_showing = self.showing_tool_panel
        if panel_was_showing:
            try:
                if self.live_display is not None:
                    self.live_display.stop()
                self.showing_tool_panel = False
            except Exception:
                pass

        try:
            # Handle content with proper formatting
            if not text.strip():
                return

            # Use Claude Code-style formatting: simple, left-aligned text with minimal processing
            try:
                # Process file links for better readability but avoid Rich markdown rendering
                processed_text = self._process_text_for_claude_code_style(text)
                self.console.print(processed_text, end="")
            except Exception:
                # Fall back to plain text
                self.console.print(text, end="")

            self.console.file.flush()

        except Exception as e:
            logger.debug(f"Error updating content: {e}")
            # Last resort fallback
            print(text, end="", flush=True)
        finally:
            # Restore the panel if it was showing
            if panel_was_showing and (self.tool_activities or self.status_info):
                try:
                    # Small delay to ensure content is rendered
                    import time

                    time.sleep(0.1)
                    self._show_bottom_tool_panel()
                except Exception:
                    pass

    def _print_wrapped_text(self, text: str, width: int) -> None:
        """Print text with proper word wrapping."""
        import textwrap

        # Split text into lines and wrap each line individually
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line.strip():  # Only wrap non-empty lines
                wrapped = textwrap.fill(
                    line.strip(),
                    width=width,
                    break_long_words=False,
                    break_on_hyphens=False,
                    expand_tabs=True,
                )
                self.console.print(wrapped, end="")

            # Add newline if not the last line or if original line was empty
            if i < len(lines) - 1:
                self.console.print()

    def _temporarily_hide_panel(self) -> None:
        """Temporarily hide the tool panel to prevent overlap."""
        if self.live_display and self.showing_tool_panel:
            try:
                self.live_display.stop()
                self._temp_live_display = self.live_display
                self.live_display = None
                self.showing_tool_panel = False
            except Exception:
                pass

    def _restore_panel(self) -> None:
        """Restore the tool panel after content output."""
        if hasattr(self, "_temp_live_display") and self._temp_live_display:
            try:
                # Wait a brief moment for content to finish
                import time

                time.sleep(0.2)
                # Recreate the panel with current activities or status
                if self.tool_activities or self.status_info:
                    self._show_bottom_tool_panel()
                delattr(self, "_temp_live_display")
            except Exception:
                pass

    def _has_markdown_patterns(self, text: str) -> bool:
        """Check if text contains markdown patterns."""
        if not text or len(text.strip()) < 20:
            return False

        # Check for common markdown patterns
        lines = text.split("\n")
        markdown_indicators = [
            lambda line: line.strip().startswith("#"),  # Headers
            lambda line: line.strip().startswith("```"),  # Code blocks
            lambda line: line.strip().startswith("- ")
            or line.strip().startswith("* "),  # Lists
            lambda line: "**" in line or "__" in line,  # Bold
            lambda line: line.strip().startswith("> "),  # Quotes
            lambda line: "`" in line and line.count("`") >= 2,  # Inline code
        ]

        return any(
            any(indicator(line) for indicator in markdown_indicators)
            for line in lines[:10]  # Check first 10 lines
        )

    def _process_text_for_claude_code_style(self, text: str) -> str:
        """Process text to match Claude Code's clean, left-aligned presentation style."""
        if not text or not text.strip():
            return text

        # Apply minimal processing to improve readability without heavy markdown rendering
        processed_text = _process_markdown_for_readability(text)

        # Remove excessive line spacing that might cause centering artifacts
        lines = processed_text.split("\n")
        cleaned_lines = []

        for line in lines:
            # Keep original line structure but ensure consistent formatting
            cleaned_lines.append(line.rstrip())  # Remove trailing whitespace

        return "\n".join(cleaned_lines)

    def update_status_info(self, info_lines: List[str]) -> None:
        """Update status info band with dynamic content.

        Args:
            info_lines: List of strings to display in the status band.
                       Will be truncated to max_info_lines.
        """
        if not self.is_active:
            return

        self.status_info = info_lines[: self.max_info_lines]
        self.current_info_lines = len(self.status_info)

        # Always update the combined panel - keep it consistent
        self._show_bottom_tool_panel()

    def _show_status_only_panel(self) -> None:
        """Show status info in a panel when no tool activities exist yet."""
        if not self.status_info:
            return

        try:
            # Create status-only content
            status_content = "\n".join(f"📊 {line}" for line in self.status_info)

            # Create status panel
            panel = Panel(
                status_content, title="Status", border_style="blue", padding=(0, 1)
            )

            if not self.showing_tool_panel:
                # Create Live display for status
                self.live_display = Live(
                    panel,
                    console=self.console,
                    screen=False,
                    auto_refresh=False,
                    refresh_per_second=1,
                    transient=False,
                    vertical_overflow="visible",
                )
                self.live_display.start()
                self.showing_tool_panel = True
                logger.debug("Started Live display for status-only panel")
            else:
                # Update existing panel
                if self.live_display and hasattr(self.live_display, "renderable"):
                    self.live_display.update(panel, refresh=True)

        except Exception as e:
            logger.debug(f"Error showing status-only panel: {e}")

    def _show_status_bar(self) -> None:
        """Show persistent status bar with elapsed time and stats."""
        # Don't show status bar separately - it will be integrated with the tool panel
        # This prevents the scrolling status bar issue
        pass

    def _update_status_info(self, event: StatusEvent) -> None:
        """Update status info from event (single line update)."""
        # For single line status updates from events
        if len(self.status_info) == 0:
            self.status_info = [event.message]
        else:
            self.status_info[0] = event.message
        self.current_info_lines = len(self.status_info)
        # Status info updates don't need to refresh display in new approach

    def _update_tool_activities(self, event: StatusEvent) -> None:
        """Update tool activities with bottom-pinned display."""
        if not self.is_active:
            logger.debug("Tool activity update ignored - display not active")
            return

        # Apply smart truncation if requested
        message = event.message
        if event.truncate_width:
            message = self.smart_truncate(message, event.truncate_width, "command")

        # Add timestamp to tool activity
        timestamp = datetime.now().strftime("%H:%M:%S")
        activity_line = f"[{timestamp}] {event.visual_cue} {message}"

        logger.debug(f"Adding tool activity: {activity_line}")

        # Add to activities and keep only recent ones
        self.tool_activities.append(activity_line)
        if len(self.tool_activities) > self.max_status_lines:
            self.tool_activities.pop(0)

        logger.debug(f"Total tool activities: {len(self.tool_activities)}")

        # Show/update the bottom-pinned tool panel
        self._show_bottom_tool_panel()

    def _show_bottom_tool_panel(self) -> None:
        """Show persistent tool panel pinned to bottom using Live display."""
        # Show panel if we have any content (status or tool activities)
        if not self.tool_activities and not self.status_info:
            return

        try:
            # Combine status info and tool activities in one panel
            panel_content_lines = []

            # Add status info at the top if available
            if self.status_info:
                for line in self.status_info:
                    panel_content_lines.append(f"📊 {line}")
                panel_content_lines.append("")  # Separator line

            # Add tool activities
            panel_content_lines.extend(self.tool_activities)

            # Create combined content
            combined_content = "\n".join(panel_content_lines)

            # Create a compact panel with both status and activities
            panel = Panel(
                combined_content,
                title="Status & Tool Activity",
                border_style="green",
                padding=(0, 1),
            )

            if not self.showing_tool_panel:
                # First time - start persistent Live display at bottom
                self.live_display = Live(
                    panel,
                    console=self.console,
                    screen=False,  # Don't take over entire screen
                    auto_refresh=False,  # Manual refresh for better control
                    refresh_per_second=1,
                    transient=False,  # Keep it persistent
                    vertical_overflow="visible",  # Let content scroll above
                )
                self.live_display.start()
                self.showing_tool_panel = True
                logger.debug("Started new Live display for tool panel")
            else:
                # Update existing panel in place - this is key for single persistent panel
                if self.live_display and hasattr(self.live_display, "renderable"):
                    self.live_display.update(panel, refresh=True)
                    logger.debug("Updated existing Live display panel")
                else:
                    # Recreate if Live display is corrupted
                    self._reset_tool_panel()
                    self._show_bottom_tool_panel()
                    return

        except Exception as e:
            logger.debug(f"Failed to show bottom tool panel: {e}")
            # Reset and try again once
            self._reset_tool_panel()
            if self.tool_activities:
                self.console.print(f"🔧 {self.tool_activities[-1]}")

    def _reset_tool_panel(self) -> None:
        """Reset the tool panel state for clean restart."""
        if self.live_display:
            try:
                self.live_display.stop()
            except Exception:
                pass
            self.live_display = None
        self.showing_tool_panel = False
        logger.debug("Reset tool panel state")

    def _hide_tool_panel(self) -> None:
        """Hide the persistent tool panel cleanly."""
        if self.showing_tool_panel and self.live_display:
            try:
                self.live_display.stop()
                self.live_display = None
                self.showing_tool_panel = False
                logger.debug("Hidden tool panel cleanly")
            except Exception as e:
                logger.debug(f"Error hiding tool panel: {e}")
                # Force reset
                self._reset_tool_panel()

    def show_final_summary(self, summary_text: str) -> None:
        """Transition to final summary view - hide tool panel and show summary cleanly."""
        # Hide the tool panel (like Claude Code interface)
        self._hide_tool_panel()

        # Print final summary in free scrolling area
        self.console.print("🤖 Claude's Problem-Solving Approach")
        self.console.print("─" * 80)

        # Use Claude Code-style summary formatting: clean and left-aligned
        try:
            processed_summary = self._process_text_for_claude_code_style(summary_text)
            self.console.print(processed_summary)
        except Exception:
            self.console.print(summary_text)

    def stop(self) -> None:
        """Stop the display and clean up."""
        # Hide tool panel cleanly
        self._hide_tool_panel()
        self.is_active = False


# TextualStreamDisplay removed - using FreeScrollStreamDisplay instead


class StatusDisplayManager:
    """Unified status display manager with graceful interruption handling."""

    def __init__(
        self,
        mode: str = StatusDisplayMode.ACTIVITY_LOG,
        console: Optional[Console] = None,
        handle_interrupts: bool = True,
    ):
        self.console = console or Console()
        self.mode = mode
        self.handle_interrupts = handle_interrupts
        self.display: Optional[BaseStatusDisplay] = None
        self.operation_name = ""
        self.interrupted = False
        self.interrupt_handler_installed = False
        self.original_sigint_handler: Optional[Union[Callable, int]] = None

    def _create_display(self) -> BaseStatusDisplay:
        """Create appropriate display based on mode."""
        if self.mode == StatusDisplayMode.PROGRESS_BAR:
            return ProgressBarDisplay(self.console)
        elif self.mode == StatusDisplayMode.ACTIVITY_LOG:
            return ActivityLogDisplay(self.console)
        elif self.mode == StatusDisplayMode.SPINNER:
            return SpinnerDisplay(self.console)
        elif self.mode == StatusDisplayMode.SILENT:
            return SilentDisplay(self.console)
        elif self.mode == StatusDisplayMode.SPLIT_STREAM:
            return SplitStreamDisplay(self.console)
        elif self.mode == StatusDisplayMode.FREE_SCROLL_STREAM:
            return FreeScrollStreamDisplay(self.console)
        else:
            raise ValueError(f"Unknown status display mode: {self.mode}")

    def _install_interrupt_handler(self):
        """Install graceful interrupt handler."""
        if not self.handle_interrupts or self.interrupt_handler_installed:
            return

        self.original_sigint_handler = signal.signal(
            signal.SIGINT, self._signal_handler
        )
        self.interrupt_handler_installed = True

    def _restore_interrupt_handler(self):
        """Restore original interrupt handler."""
        if self.interrupt_handler_installed and self.original_sigint_handler:
            signal.signal(signal.SIGINT, self.original_sigint_handler)
            self.interrupt_handler_installed = False

    def _signal_handler(self, signum, frame):
        """Handle SIGINT (Ctrl-C) gracefully."""
        self.interrupted = True
        if self.display:
            self.display.stop()
        self.console.print()  # New line
        self.console.print(
            f"🛑 Interrupting {self.operation_name.lower()}...", style="yellow"
        )
        self._restore_interrupt_handler()
        raise KeyboardInterrupt()

    @contextmanager
    def status_context(self, operation_name: str):
        """Context manager for status display with automatic cleanup."""
        self.start(operation_name)
        try:
            yield self
        finally:
            self.stop()

    def start(self, operation_name: str) -> None:
        """Start status display."""
        self.operation_name = operation_name
        self.interrupted = False
        self.display = self._create_display()

        if self.handle_interrupts:
            self._install_interrupt_handler()

        self.display.start(operation_name)

    def update(
        self,
        message: str,
        visual_cue: str = "•",
        style: str = "dim",
        event_type: str = "info",
        truncate_width: Optional[int] = None,
        **metadata,
    ) -> None:
        """Update status display with new information."""
        if not self.display or self.interrupted:
            return

        event = StatusEvent(
            message=message,
            visual_cue=visual_cue,
            style=style,
            event_type=event_type,
            metadata=metadata,
            truncate_width=truncate_width,
        )
        self.display.update(event)

    def update_content(self, text: str) -> None:
        """Update content area for split stream displays."""
        if not self.display or self.interrupted:
            return

        # Only SplitStreamDisplay and FreeScrollStreamDisplay support this method
        if hasattr(self.display, "update_content"):
            self.display.update_content(text)

    def update_status_info(self, info_lines: List[str]) -> None:
        """Update status info band (for FreeScrollStreamDisplay).

        Args:
            info_lines: List of strings to display in the dynamic status band.
                       Useful for showing running clocks, progress info, etc.
        """
        if not self.display or self.interrupted:
            return

        # Only FreeScrollStreamDisplay supports this method
        if hasattr(self.display, "update_status_info"):
            self.display.update_status_info(info_lines)

    def show_final_summary(self, summary_text: str) -> None:
        """Show final summary and transition from streaming to final view."""
        if not self.display or self.interrupted:
            return

        # Only FreeScrollStreamDisplay supports this method
        if hasattr(self.display, "show_final_summary"):
            self.display.show_final_summary(summary_text)
        else:
            # Fallback to regular format_summary for other displays
            self.format_summary(summary_text, title="Claude's Problem-Solving Approach")

    def stop(self) -> None:
        """Stop status display and cleanup."""
        if self.display:
            self.display.stop()
            self.display = None

        if self.handle_interrupts:
            self._restore_interrupt_handler()

    def format_summary(
        self, summary_text: str, title: str = "Summary", render_markdown: bool = True
    ) -> None:
        """Display a formatted summary with optional markdown rendering."""
        self.console.print(f"\n🤖 {title}")
        self.console.print("─" * 80)

        # Special handling for tool usage statistics to ensure proper line breaks
        if "📊 Tool Usage Statistics" in summary_text:
            lines = summary_text.split("\n")
            in_stats_section = False

            for line in lines:
                stripped_line = line.strip()

                if "📊 Tool Usage Statistics" in stripped_line:
                    in_stats_section = True
                    self.console.print("\n" + stripped_line, style="bold cyan")
                    continue

                if in_stats_section and stripped_line:
                    if "Operation Breakdown:" in stripped_line:
                        self.console.print("\n" + stripped_line, style="bold")
                    elif any(emoji in stripped_line for emoji in ["🔍✨", "😞", "📄"]):
                        # Operation breakdown items
                        self.console.print("  " + stripped_line)
                    elif stripped_line and not stripped_line.startswith("##"):
                        # Regular statistics lines
                        self.console.print("  " + stripped_line)
                    else:
                        self.console.print("")
                elif stripped_line:
                    # Regular narrative content - use simple text processing
                    if render_markdown and any(
                        md_char in line for md_char in ["**", "_", "#", "`", "*"]
                    ):
                        processed_line = self._process_markdown_for_readability(line)
                        self.console.print(processed_line)
                    else:
                        self.console.print(line)
                else:
                    self.console.print("")
        else:
            # Use simple text processing instead of Rich markdown to avoid centering
            if render_markdown:
                processed_summary = self._process_markdown_for_readability(summary_text)
                self.console.print(processed_summary)
            else:
                self.console.print(summary_text)

    def _process_markdown_for_readability(self, text: str) -> str:
        """Process markdown text to improve link readability by removing or simplifying dark links."""
        return _process_markdown_for_readability(text)


def _process_markdown_for_readability(text: str) -> str:
    """Process markdown text to improve readability while preserving structure."""
    import re

    # Convert markdown links [text](url) for better readability
    def replace_link(match):
        text_part = match.group(1)
        url = match.group(2)

        # For file paths, preserve them as clickable links but in a more readable format
        if url.startswith(("src/", "/", "./", "file://")) or (
            ":" in url and not url.startswith(("http", "https", "ftp"))
        ):
            # Keep file path links as they are useful for navigation
            # These will still be clickable in most terminals
            return f"[{text_part}]({url})"
        else:
            # For external URLs, remove the link to avoid dark colors but show URL
            return f"{text_part} ({url})"

    # Replace markdown links with more readable format
    processed = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, text)

    # Convert markdown bold to simple text (to avoid Rich rendering issues)
    processed = re.sub(r"\*\*([^*]+)\*\*", r"\1", processed)
    processed = re.sub(r"__([^_]+)__", r"\1", processed)

    # Convert markdown headers to simple text with prefix
    processed = re.sub(r"^### (.+)$", r"   \1", processed, flags=re.MULTILINE)
    processed = re.sub(r"^## (.+)$", r"  \1", processed, flags=re.MULTILINE)
    processed = re.sub(r"^# (.+)$", r" \1", processed, flags=re.MULTILINE)

    return processed


# Convenience functions for common use cases
def create_progress_status(console: Optional[Console] = None) -> StatusDisplayManager:
    """Create a progress bar status display."""
    return StatusDisplayManager(StatusDisplayMode.PROGRESS_BAR, console)


def create_activity_status(console: Optional[Console] = None) -> StatusDisplayManager:
    """Create an activity log status display."""
    return StatusDisplayManager(StatusDisplayMode.ACTIVITY_LOG, console)


def create_spinner_status(console: Optional[Console] = None) -> StatusDisplayManager:
    """Create a spinner status display."""
    return StatusDisplayManager(StatusDisplayMode.SPINNER, console)


def create_silent_status(console: Optional[Console] = None) -> StatusDisplayManager:
    """Create a silent status display."""
    return StatusDisplayManager(StatusDisplayMode.SILENT, console)


def create_split_stream_status(
    console: Optional[Console] = None,
) -> StatusDisplayManager:
    """Create a split stream status display for Claude streaming."""
    return StatusDisplayManager(StatusDisplayMode.SPLIT_STREAM, console)


def create_free_scroll_stream_status(
    console: Optional[Console] = None,
) -> StatusDisplayManager:
    """Create a free scroll stream status display with dynamic status band.

    Features:
    - Free scrolling content area (top)
    - Dynamic status info band (middle) - for clocks, progress, etc.
    - Fixed tool activities panel (bottom) - boxed display
    """
    return StatusDisplayManager(StatusDisplayMode.FREE_SCROLL_STREAM, console)


def create_textual_stream_status(
    console: Optional[Console] = None,
) -> StatusDisplayManager:
    """Create a free scroll stream display (replaces textual implementation).

    Features:
    - Free scrolling content using Rich console
    - Status updates at bottom

    This is the working display for Claude analysis operations.
    """
    return StatusDisplayManager(StatusDisplayMode.FREE_SCROLL_STREAM, console)


# Visual cue constants for consistency
class VisualCues:
    """Standard visual cues used across the application."""

    SEMANTIC_SEARCH = "🔍✨"
    TEXT_SEARCH = "😞"
    FILE_READ = "📖"
    FILE_WRITE = "✏️"
    FILE_OPERATION = "📄"
    GIT_OPERATION = "🌿"
    BASH_COMMAND = "⚡"
    CREATED = "✨"
    MODIFIED = "🔧"
    DELETED = "🗑️"
    ERROR = "❌"
    SUCCESS = "✅"
    WARNING = "⚠️"
    INFO = "ℹ️"
    INDEXING = "📚"
    WATCHING = "👀"
    ANALYZING = "🤖"

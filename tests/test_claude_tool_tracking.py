"""
Tests for Claude tool usage tracking functionality.

Following TDD principles - comprehensive tests written before implementation.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock
from rich.console import Console

from src.code_indexer.services.claude_tool_tracking import (
    ToolUsageEvent,
    CommandClassifier,
    ToolUsageTracker,
    StatusLineManager,
    ClaudePlanSummary,
    process_tool_use_event,
)


class TestToolUsageEvent:
    """Test the ToolUsageEvent dataclass."""

    def test_tool_usage_event_creation(self):
        """Test basic ToolUsageEvent creation."""
        event = ToolUsageEvent(
            tool_name="Bash",
            operation_type="cidx_semantic_search",
            visual_cue="🔍✨",
            target="authentication",
            command_detail="cidx query 'authentication'",
            timestamp=datetime.now(),
            status="started",
        )

        assert event.tool_name == "Bash"
        assert event.operation_type == "cidx_semantic_search"
        assert event.visual_cue == "🔍✨"
        assert event.target == "authentication"
        assert event.command_detail == "cidx query 'authentication'"
        assert event.status == "started"
        assert event.tool_use_id is None
        assert event.duration is None
        assert event.error_message is None

    def test_tool_usage_event_with_optional_fields(self):
        """Test ToolUsageEvent with all optional fields."""
        event = ToolUsageEvent(
            tool_name="Read",
            operation_type="file_operation",
            visual_cue="📖",
            target="src/auth.py",
            command_detail="Reading authentication module",
            timestamp=datetime.now(),
            status="completed",
            tool_use_id="toolu_123",
            duration=1.5,
            error_message=None,
        )

        assert event.tool_use_id == "toolu_123"
        assert event.duration == 1.5
        assert event.error_message is None


class TestCommandClassifier:
    """Test the CommandClassifier for bash command analysis."""

    def setup_method(self):
        """Set up test fixtures."""
        self.classifier = CommandClassifier()

    def test_classify_cidx_query_command(self):
        """Test classification of cidx query commands."""
        command = "cidx query 'authentication logic' --language python"
        result = self.classifier.classify_bash_command(command)

        assert result["type"] == "cidx_semantic_search"
        assert result["visual_cue"] == "🔍✨"
        assert result["priority"] == "high"
        assert "authentication logic" in result["command_summary"]

    def test_classify_grep_command(self):
        """Test classification of grep commands."""
        command = "grep -r 'password' src/"
        result = self.classifier.classify_bash_command(command)

        assert result["type"] == "grep_search"
        assert result["visual_cue"] == "😞"
        assert result["priority"] == "medium"
        assert "password" in result["command_summary"]

    def test_classify_file_operation_command(self):
        """Test classification of file operation commands."""
        command = "ls -la src/auth/"
        result = self.classifier.classify_bash_command(command)

        assert result["type"] == "file_operation"
        assert result["visual_cue"] == "📄"
        assert result["priority"] == "low"
        assert "src/auth/" in result["command_summary"]

    def test_extract_cidx_operation(self):
        """Test extraction of cidx operation details."""
        command = "cidx query 'database connection' --limit 5"
        result = self.classifier._extract_cidx_operation(command)

        assert "database connection" in result
        assert "Semantic search" in result

    def test_extract_grep_operation(self):
        """Test extraction of grep operation details."""
        command = "grep -rn 'TODO' src/ --include='*.py'"
        result = self.classifier._extract_grep_operation(command)

        assert "TODO" in result
        assert "Text search" in result

    def test_extract_file_operation(self):
        """Test extraction of file operation details."""
        command = "cat src/config/settings.py | head -20"
        result = self.classifier._extract_file_operation(command)

        assert "settings.py" in result or "Reading" in result

    def test_classify_git_command(self):
        """Test classification of git commands."""
        command = "git diff HEAD~1"
        result = self.classifier.classify_bash_command(command)

        assert result["type"] == "git_operation"
        assert result["visual_cue"] == "🌿"
        assert result["priority"] == "medium"

    def test_classify_ripgrep_command(self):
        """Test classification of ripgrep commands."""
        command = "rg 'function' --type py"
        result = self.classifier.classify_bash_command(command)

        assert result["type"] == "grep_search"
        assert result["visual_cue"] == "😞"

    def test_classify_generic_bash_command(self):
        """Test classification of generic bash commands."""
        command = "echo 'hello world'"
        result = self.classifier.classify_bash_command(command)

        assert result["type"] == "bash_command"
        assert result["visual_cue"] == "⚡"
        assert result["priority"] == "low"


class TestToolUsageTracker:
    """Test the ToolUsageTracker for event management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = ToolUsageTracker()

    def test_tracker_initialization(self):
        """Test tracker initialization."""
        tracker = ToolUsageTracker()
        assert tracker.events == []
        assert tracker.active_events == {}
        assert isinstance(tracker.start_time, datetime)

    def test_track_tool_start(self):
        """Test tracking tool start events."""
        event = ToolUsageEvent(
            tool_name="Bash",
            operation_type="cidx_semantic_search",
            visual_cue="🔍✨",
            target="auth",
            command_detail="Semantic search: 'auth'",
            timestamp=datetime.now(),
            status="started",
            tool_use_id="test_123",
        )

        self.tracker.track_tool_start(event)

        assert len(self.tracker.events) == 1
        assert "test_123" in self.tracker.active_events
        assert self.tracker.active_events["test_123"] == event

    def test_track_tool_completion(self):
        """Test tracking tool completion events."""
        # Create and start an event
        event = ToolUsageEvent(
            tool_name="Bash",
            operation_type="cidx_semantic_search",
            visual_cue="🔍✨",
            target="auth",
            command_detail="Semantic search: 'auth'",
            timestamp=datetime.now(),
            status="started",
            tool_use_id="test_456",
        )
        self.tracker.track_tool_start(event)

        # Complete the event
        result_data = {
            "tool_use_id": "test_456",
            "is_error": False,
            "content": "Found 5 results",
        }
        self.tracker.track_tool_completion(result_data)

        # Check completion
        assert event.status == "completed"
        assert event.duration is not None
        assert event.duration >= 0
        assert "test_456" not in self.tracker.active_events

    def test_track_tool_failure(self):
        """Test tracking tool failure events."""
        event = ToolUsageEvent(
            tool_name="Bash",
            operation_type="grep_search",
            visual_cue="😞",
            target="password",
            command_detail="Text search: 'password'",
            timestamp=datetime.now(),
            status="started",
            tool_use_id="test_789",
        )
        self.tracker.track_tool_start(event)

        # Fail the event
        result_data = {
            "tool_use_id": "test_789",
            "is_error": True,
            "content": "Command failed: grep: invalid option",
        }
        self.tracker.track_tool_completion(result_data)

        assert event.status == "failed"
        assert event.error_message == "Command failed: grep: invalid option"
        assert "test_789" not in self.tracker.active_events

    def test_get_current_activity(self):
        """Test getting current activity description."""
        # No activity initially
        assert self.tracker.get_current_activity() is None

        # Add an active event
        event = ToolUsageEvent(
            tool_name="Read",
            operation_type="file_operation",
            visual_cue="📖",
            target="src/auth.py",
            command_detail="Reading: src/auth.py",
            timestamp=datetime.now(),
            status="started",
            tool_use_id="read_123",
        )
        self.tracker.track_tool_start(event)

        activity = self.tracker.get_current_activity()
        assert activity == "📖 Reading: src/auth.py"

    def test_get_summary_stats_empty(self):
        """Test getting summary statistics when empty."""
        stats = self.tracker.get_summary_stats()
        expected_stats = {
            "total_events": 0,
            "session_duration": 0,
            "tools_used": [],
            "operation_counts": {},
            "cidx_usage_count": 0,
            "grep_usage_count": 0,
            "average_tool_duration": 0,
        }

        for key in expected_stats:
            assert key in stats
            if key != "session_duration":  # session_duration will be > 0
                assert stats[key] == expected_stats[key]

    def test_get_summary_stats_with_events(self):
        """Test getting summary statistics with events."""
        # Add cidx event
        cidx_event = ToolUsageEvent(
            tool_name="Bash",
            operation_type="cidx_semantic_search",
            visual_cue="🔍✨",
            target="auth",
            command_detail="Semantic search: 'auth'",
            timestamp=datetime.now(),
            status="completed",
            tool_use_id="cidx_1",
            duration=1.5,
        )
        self.tracker.track_tool_start(cidx_event)

        # Add grep event
        grep_event = ToolUsageEvent(
            tool_name="Bash",
            operation_type="grep_search",
            visual_cue="😞",
            target="password",
            command_detail="Text search: 'password'",
            timestamp=datetime.now(),
            status="completed",
            tool_use_id="grep_1",
            duration=0.8,
        )
        self.tracker.track_tool_start(grep_event)

        stats = self.tracker.get_summary_stats()

        assert stats["total_events"] == 2
        assert stats["cidx_usage_count"] == 1
        assert stats["grep_usage_count"] == 1
        assert "Bash" in stats["tools_used"]
        assert stats["completed_events"] == 2
        assert stats["average_tool_duration"] == (1.5 + 0.8) / 2

    def test_get_all_events(self):
        """Test getting all recorded events."""
        assert self.tracker.get_all_events() == []

        event = ToolUsageEvent(
            tool_name="Read",
            operation_type="file_operation",
            visual_cue="📖",
            target="test.py",
            command_detail="Reading: test.py",
            timestamp=datetime.now(),
            status="started",
            tool_use_id="read_1",
        )
        self.tracker.track_tool_start(event)

        events = self.tracker.get_all_events()
        assert len(events) == 1
        assert events[0] == event

        # Ensure it's a copy
        events.append("fake_event")
        assert len(self.tracker.get_all_events()) == 1


class TestStatusLineManager:
    """Test the StatusLineManager for real-time display."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = StatusLineManager()

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = StatusLineManager()
        assert manager.status_manager is not None
        assert manager.cidx_usage_count == 0
        assert manager.grep_usage_count == 0
        assert hasattr(manager, "visual_cues")

    def test_manager_initialization_with_console(self):
        """Test manager initialization with custom console."""
        console = Mock(spec=Console)
        manager = StatusLineManager(console=console)
        # The console is passed to the internal status manager
        assert manager.status_manager.console == console

    def test_start_display(self):
        """Test starting the display."""
        manager = StatusLineManager()
        manager.start_display()

        # Check that internal display is active
        assert manager.status_manager.display is not None
        assert manager.status_manager.display.is_active is True

        # Cleanup
        manager.stop_display()

    def test_stop_display(self):
        """Test stopping the display."""
        manager = StatusLineManager()
        manager.start_display()
        assert manager.status_manager.display is not None
        assert manager.status_manager.display.is_active is True

        manager.stop_display()
        # After stopping, the display should be cleaned up
        assert manager.status_manager.display is None

    def test_update_activity(self):
        """Test updating activity display."""
        manager = StatusLineManager()

        # Create a cidx event
        cidx_event = ToolUsageEvent(
            tool_name="Bash",
            operation_type="cidx_semantic_search",
            visual_cue="🔍✨",
            target="auth",
            command_detail="Semantic search: 'auth'",
            timestamp=datetime.now(),
            status="started",
            tool_use_id="test_cidx",
        )

        manager.update_activity(cidx_event)

        assert manager.cidx_usage_count == 1
        assert manager.grep_usage_count == 0

        # Create a grep event
        grep_event = ToolUsageEvent(
            tool_name="Bash",
            operation_type="grep_search",
            visual_cue="😞",
            target="password",
            command_detail="Text search: 'password'",
            timestamp=datetime.now(),
            status="started",
            tool_use_id="test_grep",
        )

        manager.update_activity(grep_event)

        assert manager.cidx_usage_count == 1
        assert manager.grep_usage_count == 1


class TestClaudePlanSummary:
    """Test the ClaudePlanSummary for narrative generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.summary = ClaudePlanSummary()

    def test_summary_initialization(self):
        """Test summary generator initialization."""
        summary = ClaudePlanSummary()
        assert summary is not None

    def test_generate_narrative(self):
        """Test narrative generation."""
        summary = ClaudePlanSummary()

        # Empty events
        narrative = summary.generate_narrative([])
        assert "No tool usage recorded" in narrative

        # With events
        events = [
            ToolUsageEvent(
                tool_name="Bash",
                operation_type="cidx_semantic_search",
                visual_cue="🔍✨",
                target="auth",
                command_detail="Semantic search: 'auth'",
                timestamp=datetime.now(),
                status="completed",
                duration=1.5,
            ),
            ToolUsageEvent(
                tool_name="Bash",
                operation_type="grep_search",
                visual_cue="😞",
                target="password",
                command_detail="Text search: 'password'",
                timestamp=datetime.now(),
                status="completed",
                duration=0.8,
            ),
        ]

        narrative = summary.generate_narrative(events)
        assert "Claude used 2 tools" in narrative
        assert "Preferred Approach" in narrative
        assert "Text-Based Search" in narrative

    def test_format_statistics(self):
        """Test statistics formatting."""
        summary = ClaudePlanSummary()

        # Empty events
        stats = summary.format_statistics([])
        assert "No statistics available" in stats

        # With events
        events = [
            ToolUsageEvent(
                tool_name="Bash",
                operation_type="cidx_semantic_search",
                visual_cue="🔍✨",
                target="auth",
                command_detail="Semantic search: 'auth'",
                timestamp=datetime.now(),
                status="completed",
                duration=1.5,
            )
        ]

        stats = summary.format_statistics(events)
        assert "Tool Usage Statistics" in stats
        assert "Total Operations: 1" in stats
        assert "Bash" in stats

    def test_generate_complete_summary(self):
        """Test complete summary generation."""
        summary = ClaudePlanSummary()

        # Empty events
        complete = summary.generate_complete_summary([])
        assert "No tool usage data available" in complete

        # With events
        events = [
            ToolUsageEvent(
                tool_name="Read",
                operation_type="file_operation",
                visual_cue="📖",
                target="src/auth.py",
                command_detail="Reading: src/auth.py",
                timestamp=datetime.now(),
                status="completed",
                duration=0.5,
            )
        ]

        complete = summary.generate_complete_summary(events)
        assert "Claude used 1 tools" in complete
        assert "Tool Usage Statistics" in complete


class TestProcessToolUseEvent:
    """Test the process_tool_use_event function."""

    def test_process_bash_tool_use_event(self):
        """Test processing a bash tool use event."""
        tool_data = {
            "type": "tool_use",
            "id": "toolu_123",
            "name": "Bash",
            "input": {"command": "cidx query 'authentication' --language python"},
        }
        classifier = Mock(spec=CommandClassifier)
        classifier.classify_bash_command.return_value = {
            "type": "cidx_semantic_search",
            "visual_cue": "🔍✨",
            "priority": "high",
            "command_summary": "Semantic search: 'authentication'",
        }

        event = process_tool_use_event(tool_data, classifier)

        assert event.tool_name == "Bash"
        assert event.operation_type == "cidx_semantic_search"
        assert event.visual_cue == "🔍✨"
        assert event.tool_use_id == "toolu_123"
        assert event.status == "started"
        assert "cidx query 'authentication'" in event.target
        assert event.command_detail == "Semantic search: 'authentication'"

    def test_process_read_tool_use_event(self):
        """Test processing a read tool use event."""
        tool_data = {
            "type": "tool_use",
            "id": "toolu_456",
            "name": "Read",
            "input": {"file_path": "src/auth.py"},
        }
        classifier = Mock(spec=CommandClassifier)

        event = process_tool_use_event(tool_data, classifier)

        assert event.tool_name == "Read"
        assert event.operation_type == "file_operation"
        assert event.visual_cue == "📖"
        assert event.tool_use_id == "toolu_456"
        assert event.status == "started"
        assert event.target == "src/auth.py"
        assert event.command_detail == "Reading: src/auth.py"

    def test_process_grep_tool_use_event(self):
        """Test processing a grep tool use event."""
        tool_data = {
            "type": "tool_use",
            "id": "toolu_789",
            "name": "Grep",
            "input": {"pattern": "authentication", "include": "*.py"},
        }
        classifier = Mock(spec=CommandClassifier)

        event = process_tool_use_event(tool_data, classifier)

        assert event.tool_name == "Grep"
        assert event.operation_type == "grep_search"
        assert event.visual_cue == "😞"
        assert event.tool_use_id == "toolu_789"
        assert event.status == "started"
        assert event.target == "authentication"
        assert event.command_detail == "Text search: 'authentication' (include=*.py)"


# Mock data for testing
@pytest.fixture
def sample_cidx_event():
    """Sample cidx tool usage event."""
    return ToolUsageEvent(
        tool_name="Bash",
        operation_type="cidx_semantic_search",
        visual_cue="🔍✨",
        target="authentication",
        command_detail="cidx query 'authentication' --language python",
        timestamp=datetime.now(),
        status="started",
        tool_use_id="toolu_cidx_123",
    )


@pytest.fixture
def sample_grep_event():
    """Sample grep tool usage event."""
    return ToolUsageEvent(
        tool_name="Bash",
        operation_type="grep_search",
        visual_cue="😞",
        target="password",
        command_detail="grep -r 'password' src/",
        timestamp=datetime.now(),
        status="started",
        tool_use_id="toolu_grep_456",
    )


@pytest.fixture
def sample_read_event():
    """Sample read tool usage event."""
    return ToolUsageEvent(
        tool_name="Read",
        operation_type="file_operation",
        visual_cue="📖",
        target="src/auth.py",
        command_detail="Reading authentication module",
        timestamp=datetime.now(),
        status="completed",
        tool_use_id="toolu_read_789",
        duration=0.5,
    )


@pytest.fixture
def mock_console():
    """Mock Rich console for testing."""
    return Mock(spec=Console)


@pytest.fixture
def mock_tool_data_bash_cidx():
    """Mock tool_use JSON data for bash cidx command."""
    return {
        "type": "tool_use",
        "id": "toolu_123abc",
        "name": "Bash",
        "input": {
            "command": "cidx query 'database connection' --language python --limit 5"
        },
    }


@pytest.fixture
def mock_tool_data_bash_grep():
    """Mock tool_use JSON data for bash grep command."""
    return {
        "type": "tool_use",
        "id": "toolu_456def",
        "name": "Bash",
        "input": {"command": "grep -rn 'TODO' src/ --include='*.py'"},
    }


@pytest.fixture
def mock_tool_result_data():
    """Mock tool_result JSON data."""
    return {
        "type": "tool_result",
        "tool_use_id": "toolu_123abc",
        "is_error": False,
        "content": "Found 8 results for database connection query",
    }

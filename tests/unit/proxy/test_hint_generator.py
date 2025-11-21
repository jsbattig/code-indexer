"""Unit tests for HintGenerator and ActionableHint.

Tests cover:
- Hint generation for different command types
- Error category detection
- Hint formatting
- Context-aware hint selection
- Conversation requirement: query failures suggest grep
"""

from code_indexer.proxy.hint_generator import (
    HintGenerator,
    ActionableHint,
    ErrorCategoryDetector,
)


class TestActionableHint:
    """Test ActionableHint dataclass structure."""

    def test_actionable_hint_creation(self):
        """Test creating ActionableHint with all fields."""
        hint = ActionableHint(
            message="Test message",
            suggested_commands=["cmd1", "cmd2"],
            explanation="Test explanation",
        )

        assert hint.message == "Test message"
        assert hint.suggested_commands == ["cmd1", "cmd2"]
        assert hint.explanation == "Test explanation"

    def test_actionable_hint_without_explanation(self):
        """Test creating ActionableHint without explanation."""
        hint = ActionableHint(message="Test message", suggested_commands=["cmd1"])

        assert hint.message == "Test message"
        assert hint.suggested_commands == ["cmd1"]
        assert hint.explanation is None


class TestHintGeneratorQueryFailures:
    """Test hint generation for query command failures.

    CONVERSATION CRITICAL: Query failures must suggest grep/rg as alternatives.
    """

    def setup_method(self):
        """Initialize HintGenerator for each test."""
        self.generator = HintGenerator()

    def test_query_failure_filesystem_connection_suggests_grep(self):
        """Test query failure with Filesystem connection error suggests grep."""
        hint = self.generator.generate_hint(
            command="query",
            error_text="Cannot connect to Filesystem service at port 6333",
            repository="backend/auth-service",
        )

        # CONVERSATION REQUIREMENT: Must suggest grep
        assert "grep" in hint.message.lower()
        assert any("grep -r" in cmd for cmd in hint.suggested_commands)

        # Should also suggest rg (ripgrep) as alternative
        assert any("rg" in cmd for cmd in hint.suggested_commands) or any(
            "grep" in cmd for cmd in hint.suggested_commands
        )

        # Should mention the repository name
        assert "backend/auth-service" in hint.message

        # Should have explanation about Filesystem unavailability
        assert hint.explanation is not None
        assert (
            "filesystem" in hint.explanation.lower()
            or "service" in hint.explanation.lower()
        )

    def test_query_failure_with_search_term_in_commands(self):
        """Test that suggested grep commands include placeholder for search term."""
        hint = self.generator.generate_hint(
            command="query",
            error_text="Connection refused",
            repository="frontend/dashboard",
        )

        # Commands should include placeholder for search term
        grep_commands = [cmd for cmd in hint.suggested_commands if "grep" in cmd]
        assert len(grep_commands) > 0
        assert any(
            "your-search-term" in cmd or "search" in cmd for cmd in grep_commands
        )

    def test_query_failure_suggests_status_check(self):
        """Test query failure suggests checking cidx status."""
        hint = self.generator.generate_hint(
            command="query",
            error_text="Filesystem not running",
            repository="backend/auth",
        )

        # Should suggest checking status
        assert any("cidx status" in cmd for cmd in hint.suggested_commands)

    def test_query_failure_generic_error(self):
        """Test query failure with generic error still suggests grep."""
        hint = self.generator.generate_hint(
            command="query", error_text="Unknown query error", repository="backend/api"
        )

        # Should still suggest grep as fallback
        assert any("grep" in cmd or "rg" in cmd for cmd in hint.suggested_commands)


class TestHintGeneratorContainerFailures:
    """Test hint generation for container-related command failures."""

    def setup_method(self):
        """Initialize HintGenerator for each test."""
        self.generator = HintGenerator()

    def test_start_failure_port_conflict(self):
        """Test start failure with port conflict suggests checking ports."""
        hint = self.generator.generate_hint(
            command="start",
            error_text="Port 6333 already in use",
            repository="backend/auth",
        )

        # Should mention port conflict
        assert "port" in hint.message.lower()

        # Should suggest checking running containers
        assert any(
            "docker ps" in cmd or "podman ps" in cmd for cmd in hint.suggested_commands
        )

    def test_start_failure_docker_unavailable(self):
        """Test start failure with Docker unavailable."""
        hint = self.generator.generate_hint(
            command="start",
            error_text="Cannot connect to Docker daemon",
            repository="backend/auth",
        )

        # Should suggest checking Docker/Podman status
        assert any(
            "systemctl status docker" in cmd or "systemctl status podman" in cmd
            for cmd in hint.suggested_commands
        )

        # Should mention container runtime
        assert (
            "docker" in hint.message.lower()
            or "podman" in hint.message.lower()
            or "container" in hint.message.lower()
        )

    def test_stop_failure_generic(self):
        """Test stop failure with generic error."""
        hint = self.generator.generate_hint(
            command="stop",
            error_text="Failed to stop container",
            repository="backend/api",
        )

        # Should suggest navigating to repository
        assert any("cd backend/api" in cmd for cmd in hint.suggested_commands)

        # Should suggest checking status
        assert any("cidx status" in cmd for cmd in hint.suggested_commands)


class TestHintGeneratorStatusFailures:
    """Test hint generation for status check failures."""

    def setup_method(self):
        """Initialize HintGenerator for each test."""
        self.generator = HintGenerator()

    def test_status_failure_suggests_fix_config(self):
        """Test status failure suggests fix-config."""
        hint = self.generator.generate_hint(
            command="status",
            error_text="Configuration validation failed",
            repository="backend/auth",
        )

        # Should suggest fix-config
        assert any("cidx fix-config" in cmd for cmd in hint.suggested_commands)

        # Should suggest navigating to repository
        assert any("cd backend/auth" in cmd for cmd in hint.suggested_commands)


class TestHintGeneratorConfigFailures:
    """Test hint generation for configuration failures."""

    def setup_method(self):
        """Initialize HintGenerator for each test."""
        self.generator = HintGenerator()

    def test_config_failure_suggests_manual_inspection(self):
        """Test config failure suggests manual inspection."""
        hint = self.generator.generate_hint(
            command="fix-config",
            error_text="Cannot repair configuration",
            repository="backend/auth",
        )

        # Should suggest manual inspection
        assert "manual" in hint.message.lower() or "inspect" in hint.message.lower()

        # Should suggest checking config file
        assert any("config.json" in cmd for cmd in hint.suggested_commands)

        # Should suggest init --force as last resort
        assert any("cidx init --force" in cmd for cmd in hint.suggested_commands)


class TestHintGeneratorGeneric:
    """Test generic hint generation for unknown commands."""

    def setup_method(self):
        """Initialize HintGenerator for each test."""
        self.generator = HintGenerator()

    def test_unknown_command_generic_hint(self):
        """Test unknown command gets generic hint."""
        hint = self.generator.generate_hint(
            command="unknown-command",
            error_text="Command failed",
            repository="backend/auth",
        )

        # Should suggest navigating to repository
        assert any("cd backend/auth" in cmd for cmd in hint.suggested_commands)

        # Should suggest running command directly
        assert any("cidx unknown-command" in cmd for cmd in hint.suggested_commands)


class TestErrorCategoryDetector:
    """Test error category detection from error messages."""

    def setup_method(self):
        """Initialize ErrorCategoryDetector for each test."""
        self.detector = ErrorCategoryDetector()

    def test_detect_connection_error(self):
        """Test detection of connection errors."""
        assert (
            self.detector.detect_category("Cannot connect to service") == "connection"
        )
        assert self.detector.detect_category("Connection refused") == "connection"
        assert self.detector.detect_category("Filesystem not running") == "connection"

    def test_detect_port_conflict(self):
        """Test detection of port conflict errors."""
        assert (
            self.detector.detect_category("Port 6333 already in use") == "port_conflict"
        )
        assert (
            self.detector.detect_category("Address already in use") == "port_conflict"
        )
        assert (
            self.detector.detect_category("Bind failed on port 8080") == "port_conflict"
        )

    def test_detect_permission_error(self):
        """Test detection of permission errors."""
        assert self.detector.detect_category("Permission denied") == "permission"
        assert (
            self.detector.detect_category("Access denied to resource") == "permission"
        )
        assert self.detector.detect_category("Forbidden operation") == "permission"

    def test_detect_configuration_error(self):
        """Test detection of configuration errors."""
        assert self.detector.detect_category("Invalid config file") == "configuration"
        assert (
            self.detector.detect_category("Missing config parameter") == "configuration"
        )
        assert self.detector.detect_category("Config error detected") == "configuration"

    def test_detect_timeout_error(self):
        """Test detection of timeout errors."""
        assert self.detector.detect_category("Operation timeout") == "timeout"
        assert self.detector.detect_category("Request timed out") == "timeout"
        assert self.detector.detect_category("Deadline exceeded") == "timeout"

    def test_detect_unknown_error(self):
        """Test detection of unknown error category."""
        assert self.detector.detect_category("Random error message") == "unknown"
        assert self.detector.detect_category("Something went wrong") == "unknown"


class TestHintFormattingIntegration:
    """Test hint formatting when integrated with error messages."""

    def setup_method(self):
        """Initialize HintGenerator for each test."""
        self.generator = HintGenerator()

    def test_hint_format_structure(self):
        """Test that hints have proper structure for formatting."""
        hint = self.generator.generate_hint(
            command="query",
            error_text="Cannot connect to Filesystem",
            repository="backend/auth",
        )

        # Should have all required fields
        assert isinstance(hint.message, str)
        assert isinstance(hint.suggested_commands, list)
        assert len(hint.suggested_commands) > 0
        assert hint.explanation is None or isinstance(hint.explanation, str)

    def test_hint_commands_are_actionable(self):
        """Test that suggested commands are concrete and actionable."""
        hint = self.generator.generate_hint(
            command="start", error_text="Port conflict", repository="backend/auth"
        )

        # All commands should be concrete (no empty strings)
        for cmd in hint.suggested_commands:
            assert len(cmd.strip()) > 0
            # Commands should not be just placeholders
            assert not cmd.startswith("...")
            assert not cmd == "TODO"


class TestConversationRequirements:
    """Test specific conversation requirements are met.

    CRITICAL: These tests validate the explicit conversation requirement:
    "clearly stating so and hinting claude code to use grep or other means to search in that repo"
    """

    def setup_method(self):
        """Initialize HintGenerator for each test."""
        self.generator = HintGenerator()

    def test_query_failure_explicitly_mentions_grep(self):
        """Test that query failures explicitly mention grep in the hint message.

        CONVERSATION REQUIREMENT: Must clearly state to use grep.
        """
        hint = self.generator.generate_hint(
            command="query",
            error_text="Filesystem connection failed",
            repository="backend/auth-service",
        )

        # CRITICAL: Message must explicitly mention grep
        assert "grep" in hint.message.lower()

    def test_query_failure_provides_grep_command_example(self):
        """Test that query failures provide concrete grep command examples.

        CONVERSATION REQUIREMENT: Must hint at using grep or other means.
        """
        hint = self.generator.generate_hint(
            command="query",
            error_text="Cannot connect to Filesystem",
            repository="my-repo",
        )

        # Must have at least one grep command
        grep_commands = [cmd for cmd in hint.suggested_commands if "grep" in cmd]
        assert len(grep_commands) > 0

        # Grep command should include repository path
        assert any("my-repo" in cmd for cmd in grep_commands)

    def test_query_failure_suggests_alternative_search_tools(self):
        """Test that query failures suggest alternative search methods.

        CONVERSATION REQUIREMENT: "or other means to search in that repo"
        """
        hint = self.generator.generate_hint(
            command="query", error_text="Service unavailable", repository="test-repo"
        )

        # Should suggest multiple search alternatives
        commands_str = " ".join(hint.suggested_commands).lower()

        # At least grep should be mentioned (can also check rg/ripgrep as alternatives)
        assert "grep" in commands_str or "rg" in commands_str

    def test_query_failure_explains_why_alternative_needed(self):
        """Test that query failures explain why alternatives are needed.

        User should understand WHY they need to use grep (service unavailable).
        """
        hint = self.generator.generate_hint(
            command="query",
            error_text="Filesystem service not responding",
            repository="test-repo",
        )

        # Should have explanation
        assert hint.explanation is not None
        # Explanation should mention service unavailability or similar
        assert any(
            word in hint.explanation.lower()
            for word in ["service", "unavailable", "filesystem", "not available"]
        )

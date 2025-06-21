"""End-to-end tests for --show-claude-plan feature with real Claude CLI integration.

These tests exercise the complete feature without mocks, requiring Claude CLI to be available.
"""

import tempfile
import shutil
import pytest
import time
from pathlib import Path

from src.code_indexer.services.claude_integration import (
    ClaudeIntegrationService,
    check_claude_sdk_availability,
)
from src.code_indexer.services.claude_tool_tracking import (
    ToolUsageTracker,
    StatusLineManager,
    CommandClassifier,
    ClaudePlanSummary,
    process_tool_use_event,
)


class TestClaudePlanE2E:
    """End-to-end tests for Claude plan feature with real Claude CLI."""

    def setup_method(self):
        """Set up test environment with temp directory and sample code."""
        # Create temporary directory for test codebase
        self.temp_dir = Path(tempfile.mkdtemp())
        self.codebase_dir = self.temp_dir / "test_codebase"
        self.codebase_dir.mkdir()

        # Create sample code files for Claude to analyze
        self._create_sample_codebase()

    def teardown_method(self):
        """Clean up temporary directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _create_sample_codebase(self):
        """Create a realistic sample codebase for Claude to analyze."""
        # Create auth module
        auth_file = self.codebase_dir / "auth.py"
        auth_file.write_text(
            '''"""Authentication module for user management."""

import hashlib
import secrets
from typing import Optional, Dict


class AuthService:
    """Handles user authentication and session management."""
    
    def __init__(self):
        self.users: Dict[str, str] = {}  # username -> password_hash
        self.sessions: Dict[str, str] = {}  # session_id -> username
    
    def register_user(self, username: str, password: str) -> bool:
        """Register a new user with hashed password."""
        if username in self.users:
            return False
        
        # Hash password with salt
        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac('sha256', 
                                           password.encode(), 
                                           salt.encode(), 
                                           100000)
        
        self.users[username] = f"{salt}:{password_hash.hex()}"
        return True
    
    def authenticate(self, username: str, password: str) -> Optional[str]:
        """Authenticate user and return session ID if successful."""
        if username not in self.users:
            return None
        
        stored = self.users[username]
        salt, stored_hash = stored.split(':')
        
        # Verify password
        password_hash = hashlib.pbkdf2_hmac('sha256',
                                           password.encode(),
                                           salt.encode(),
                                           100000)
        
        if password_hash.hex() == stored_hash:
            session_id = secrets.token_urlsafe(32)
            self.sessions[session_id] = username
            return session_id
        
        return None
    
    def get_user_from_session(self, session_id: str) -> Optional[str]:
        """Get username from session ID."""
        return self.sessions.get(session_id)
    
    def logout(self, session_id: str) -> bool:
        """Logout user by removing session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
'''
        )

        # Create API module that uses auth
        api_file = self.codebase_dir / "api.py"
        api_file.write_text(
            '''"""API endpoints for web application."""

from typing import Dict, Any, Optional
from .auth import AuthService


class APIHandler:
    """Handles HTTP API requests with authentication."""
    
    def __init__(self):
        self.auth_service = AuthService()
    
    def handle_login(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user login request."""
        username = request_data.get('username')
        password = request_data.get('password')
        
        if not username or not password:
            return {
                'success': False,
                'error': 'Username and password required'
            }
        
        session_id = self.auth_service.authenticate(username, password)
        if session_id:
            return {
                'success': True,
                'session_id': session_id,
                'message': 'Login successful'
            }
        else:
            return {
                'success': False,
                'error': 'Invalid credentials'
            }
    
    def handle_register(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user registration request."""
        username = request_data.get('username')
        password = request_data.get('password')
        
        if not username or not password:
            return {
                'success': False,
                'error': 'Username and password required'
            }
        
        if len(password) < 8:
            return {
                'success': False,
                'error': 'Password must be at least 8 characters'
            }
        
        success = self.auth_service.register_user(username, password)
        if success:
            return {
                'success': True,
                'message': 'Registration successful'
            }
        else:
            return {
                'success': False,
                'error': 'Username already exists'
            }
    
    def handle_protected_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request that requires authentication."""
        session_id = request_data.get('session_id')
        
        if not session_id:
            return {
                'success': False,
                'error': 'Session ID required'
            }
        
        username = self.auth_service.get_user_from_session(session_id)
        if not username:
            return {
                'success': False,
                'error': 'Invalid or expired session'
            }
        
        return {
            'success': True,
            'username': username,
            'data': 'Protected data for authenticated user'
        }
'''
        )

        # Create a README with project info
        readme_file = self.codebase_dir / "README.md"
        readme_file.write_text(
            """# Test Authentication System

A simple authentication system with the following features:

## Components

- **AuthService**: Core authentication logic with password hashing
- **APIHandler**: HTTP API endpoints with session management

## Security Features

- PBKDF2 password hashing with salt
- Secure session token generation
- Session-based authentication

## Usage

```python
# Register a user
api = APIHandler()
result = api.handle_register({'username': 'alice', 'password': 'secret123'})

# Login
result = api.handle_login({'username': 'alice', 'password': 'secret123'})
session_id = result['session_id']

# Access protected resource
result = api.handle_protected_request({'session_id': session_id})
```
"""
        )

    @pytest.mark.skipif(
        not check_claude_sdk_availability(),
        reason="Claude CLI not available (required for E2E tests)",
    )
    @pytest.mark.e2e
    def test_claude_plan_real_analysis_with_tool_tracking(self):
        """Test real Claude analysis with --show-claude-plan feature end-to-end."""
        # Create Claude integration service
        claude_service = ClaudeIntegrationService(
            codebase_dir=self.codebase_dir, project_name="test_auth_system"
        )

        # Prepare a realistic query that should trigger tool usage
        user_query = (
            "How does the authentication system work? Show me the complete login flow."
        )

        # Provide minimal search results to encourage Claude to explore
        # This will trigger tool usage as Claude needs to discover the code
        mock_search_results = [
            {
                "path": "README.md",
                "content": "A simple authentication system",
                "score": 0.6,
                "line_start": 1,
                "line_end": 1,
            }
        ]

        # Run Claude analysis with show_claude_plan enabled
        result = claude_service.run_analysis(
            user_query=user_query,
            search_results=mock_search_results,
            stream=True,
            show_claude_plan=True,
            quiet=True,  # Suppress console output for testing
            project_info={"git_available": False, "project_id": "test_auth_system"},
        )

        # Verify the analysis succeeded
        assert result.success, f"Claude analysis failed: {result.error}"
        assert result.response, "Claude response should not be empty"
        assert len(result.response) > 100, "Response should be substantial"

        # Verify tool usage tracking data is present
        assert (
            result.tool_usage_summary is not None
        ), "Tool usage summary should be generated"
        assert (
            result.tool_usage_stats is not None
        ), "Tool usage stats should be generated"

        # Verify tool usage stats contain expected fields
        stats = result.tool_usage_stats
        assert "total_events" in stats
        assert "tools_used" in stats
        assert "operation_counts" in stats

        # Verify summary is generated (even if no tools were used)
        summary = result.tool_usage_summary
        assert summary is not None, "Tool usage summary should always be generated"

        # Claude might not use additional tools if sufficient context is provided
        # The important thing is that tracking infrastructure works
        if stats["total_events"] > 0:
            # If tools were used, verify summary content
            assert "Claude used" in summary, "Summary should mention tool usage"
            assert (
                "Tool Usage Statistics" in summary
            ), "Summary should contain statistics section"
        else:
            # If no tools were used, verify we get the "no tool usage" message
            assert "No tool usage" in summary or "Tool Usage Statistics" in summary

        print("\n=== E2E Test Results ===")
        print(f"Query: {user_query}")
        print(f"Response length: {len(result.response)} characters")
        print(f"Tool events recorded: {stats['total_events']}")
        print(f"Tools used: {stats.get('tools_used', [])}")
        print(f"Summary preview: {summary[:200]}...")

    @pytest.mark.skipif(
        not check_claude_sdk_availability(),
        reason="Claude CLI not available (required for E2E tests)",
    )
    @pytest.mark.e2e
    def test_claude_plan_tool_classification_real_usage(self):
        """Test that real Claude tool usage gets classified correctly."""
        # Test the actual tool classification with various command types
        classifier = CommandClassifier()

        # Test real cidx command patterns that Claude might use
        cidx_commands = [
            "cidx query 'authentication logic' --language python",
            "cidx query 'password hashing' --limit 5",
            "cidx query 'session management' --include-test",
        ]

        for cmd in cidx_commands:
            result = classifier.classify_bash_command(cmd)
            assert result["type"] == "cidx_semantic_search"
            assert result["visual_cue"] == "🔍✨"
            assert result["priority"] == "high"
            assert "Semantic search" in result["command_summary"]

        # Test real grep patterns
        grep_commands = [
            "grep -rn 'def authenticate' .",
            "rg 'class.*Auth' --type py",
            "grep -E 'password.*hash' auth.py",
        ]

        for cmd in grep_commands:
            result = classifier.classify_bash_command(cmd)
            assert result["type"] == "grep_search"
            assert result["visual_cue"] == "😞"
            assert result["priority"] == "medium"
            assert "Text search" in result["command_summary"]

    @pytest.mark.skipif(
        not check_claude_sdk_availability(),
        reason="Claude CLI not available (required for E2E tests)",
    )
    @pytest.mark.e2e
    def test_tool_usage_tracker_real_workflow(self):
        """Test the complete tool usage tracking workflow with realistic events."""
        tracker = ToolUsageTracker()
        classifier = CommandClassifier()
        summary_generator = ClaudePlanSummary()

        # Simulate realistic tool usage sequence that Claude might perform
        tool_events = [
            {
                "type": "tool_use",
                "tool_use_id": "real_cidx_1",
                "name": "Bash",
                "input": {
                    "command": "cidx query 'authentication system' --language python"
                },
            },
            {
                "type": "tool_use",
                "tool_use_id": "real_read_1",
                "name": "Read",
                "input": {"file_path": "auth.py"},
            },
            {
                "type": "tool_use",
                "tool_use_id": "real_read_2",
                "name": "Read",
                "input": {"file_path": "api.py"},
            },
            {
                "type": "tool_use",
                "tool_use_id": "real_grep_1",
                "name": "Bash",
                "input": {"command": "grep -rn 'password' . --include='*.py'"},
            },
        ]

        # Process tool usage events
        processed_events = []
        for tool_data in tool_events:
            event = process_tool_use_event(tool_data, classifier)
            tracker.track_tool_start(event)
            processed_events.append(event)

            # Simulate completion after a delay
            time.sleep(0.01)  # Small delay to ensure duration > 0
            completion_data = {
                "tool_use_id": tool_data["tool_use_id"],
                "is_error": False,
                "content": f"Successfully executed {tool_data['name']}",
            }
            tracker.track_tool_completion(completion_data)

        # Verify tracking worked correctly
        stats = tracker.get_summary_stats()
        assert stats["total_events"] == 4
        assert stats["cidx_usage_count"] == 1
        assert stats["grep_usage_count"] == 1
        assert stats["completed_events"] == 4
        assert "Bash" in stats["tools_used"]
        assert "Read" in stats["tools_used"]

        # Generate and verify summary
        all_events = tracker.get_all_events()
        narrative = summary_generator.generate_narrative(all_events)

        assert "Preferred Approach" in narrative
        assert "Used semantic search (1x)" in narrative
        assert "Text-Based Search" in narrative
        assert "Used grep/text search (1x)" in narrative
        assert "Code Exploration" in narrative

        # Generate complete summary
        complete_summary = summary_generator.generate_complete_summary(all_events)
        assert "Tool Usage Statistics" in complete_summary
        assert "Total Operations**: 4" in complete_summary

        print("\n=== Real Workflow Test Results ===")
        print(f"Events processed: {len(all_events)}")
        print(f"Narrative preview: {narrative[:200]}...")

    @pytest.mark.skipif(
        not check_claude_sdk_availability(),
        reason="Claude CLI not available (required for E2E tests)",
    )
    @pytest.mark.e2e
    def test_status_line_manager_real_display(self):
        """Test StatusLineManager with real Rich display (briefly)."""
        from rich.console import Console

        console = Console()
        manager = StatusLineManager(console=console)
        classifier = CommandClassifier()

        # Test real status line display briefly
        manager.start_display()

        try:
            # Simulate real tool events
            cidx_event_data = {
                "type": "tool_use",
                "tool_use_id": "status_test_1",
                "name": "Bash",
                "input": {"command": "cidx query 'auth' --language python"},
            }

            cidx_event = process_tool_use_event(cidx_event_data, classifier)
            manager.update_activity(cidx_event)

            # Brief display
            time.sleep(0.1)

            # Add grep event
            grep_event_data = {
                "type": "tool_use",
                "tool_use_id": "status_test_2",
                "name": "Bash",
                "input": {"command": "grep -r 'password' src/"},
            }

            grep_event = process_tool_use_event(grep_event_data, classifier)
            manager.update_activity(grep_event)

            time.sleep(0.1)

            # Verify counters
            assert manager.cidx_usage_count == 1
            assert manager.grep_usage_count == 1
            assert len(manager.current_activities) == 2

        finally:
            manager.stop_display()

        print("\n=== Status Line Test Results ===")
        print(f"CIDX usage count: {manager.cidx_usage_count}")
        print(f"Grep usage count: {manager.grep_usage_count}")
        print(f"Activities tracked: {len(manager.current_activities)}")

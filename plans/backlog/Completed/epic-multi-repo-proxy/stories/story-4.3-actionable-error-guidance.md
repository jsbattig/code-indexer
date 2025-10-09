# Story: Actionable Error Guidance

## Story ID: STORY-4.3
## Feature: FEAT-004 (Error Handling and Partial Success)
## Priority: P1 - Essential
## Size: Small

## User Story
**As a** developer encountering search failures
**I want to** receive hints about alternative approaches
**So that** I can work around issues effectively

## Conversation Context
**Citation**: "clearly stating so and hinting claude code to use grep or other means to search in that repo"

**Context**: The conversation specified that when query operations fail in specific repositories, the error message should provide actionable hints such as using grep or other alternative search methods. This ensures developers have immediate workarounds and aren't blocked by individual repository failures.

## Acceptance Criteria
- [ ] Query failures suggest using grep or manual search
- [ ] Container errors suggest checking Docker/Podman status
- [ ] Configuration errors suggest running fix-config
- [ ] Hints are contextual to the error type and command
- [ ] Each error type has specific, actionable guidance
- [ ] Hints include concrete commands to try
- [ ] Navigation suggestions provided when appropriate

## Technical Implementation

### 1. Hint Generation System
```python
# proxy/hint_generator.py
from typing import Optional
from dataclasses import dataclass

@dataclass
class ActionableHint:
    """Actionable hint for resolving errors"""
    message: str
    suggested_commands: List[str]
    explanation: Optional[str] = None

class HintGenerator:
    """Generate contextual hints based on error type and command"""

    def generate_hint(
        self,
        command: str,
        error_text: str,
        repository: str
    ) -> ActionableHint:
        """
        Generate actionable hint based on context.

        Args:
            command: The command that failed (query, start, etc.)
            error_text: The error message
            repository: Repository path

        Returns:
            ActionableHint with specific guidance
        """
        # Command-specific hints
        if command == 'query':
            return self._hint_for_query_failure(error_text, repository)
        elif command in ['start', 'stop']:
            return self._hint_for_container_failure(error_text, repository)
        elif command == 'status':
            return self._hint_for_status_failure(error_text, repository)
        elif command == 'fix-config':
            return self._hint_for_config_failure(error_text, repository)
        else:
            return self._generic_hint(command, repository)

    def _hint_for_query_failure(
        self,
        error_text: str,
        repository: str
    ) -> ActionableHint:
        """
        Generate hint for query command failures.

        As per conversation: "hinting claude code to use grep or other means"
        """
        if 'qdrant' in error_text.lower() or 'connect' in error_text.lower():
            return ActionableHint(
                message=f"Use grep or other search tools to search '{repository}' manually",
                suggested_commands=[
                    f"grep -r 'your-search-term' {repository}",
                    f"cd {repository} && cidx status",
                    f"cd {repository} && cidx start"
                ],
                explanation="Qdrant service not available - alternative search methods can still find code"
            )
        else:
            return ActionableHint(
                message=f"Search '{repository}' using alternative methods",
                suggested_commands=[
                    f"grep -r 'your-search-term' {repository}",
                    f"rg 'your-search-term' {repository}",
                    f"cd {repository} && cidx fix-config"
                ],
                explanation="Semantic search unavailable - use text-based search tools"
            )

    def _hint_for_container_failure(
        self,
        error_text: str,
        repository: str
    ) -> ActionableHint:
        """Generate hint for container-related failures"""
        if 'port' in error_text.lower():
            return ActionableHint(
                message="Check for port conflicts with existing containers",
                suggested_commands=[
                    "docker ps",
                    "podman ps",
                    f"cd {repository} && cidx status",
                    f"cd {repository} && cidx fix-config"
                ],
                explanation="Port already in use - need to resolve conflict"
            )
        elif 'docker' in error_text.lower() or 'podman' in error_text.lower():
            return ActionableHint(
                message="Ensure Docker/Podman is running and accessible",
                suggested_commands=[
                    "systemctl status docker",
                    "systemctl status podman",
                    "docker ps",
                    "podman ps"
                ],
                explanation="Container runtime not accessible"
            )
        else:
            return ActionableHint(
                message=f"Navigate to repository and check container status",
                suggested_commands=[
                    f"cd {repository}",
                    "cidx status",
                    "cidx start"
                ],
                explanation="Container operation failed - investigate in repository context"
            )

    def _hint_for_status_failure(
        self,
        error_text: str,
        repository: str
    ) -> ActionableHint:
        """Generate hint for status check failures"""
        return ActionableHint(
            message=f"Navigate to '{repository}' to investigate configuration",
            suggested_commands=[
                f"cd {repository}",
                "cidx fix-config",
                "cidx start"
            ],
            explanation="Status check failed - may need configuration repair"
        )

    def _hint_for_config_failure(
        self,
        error_text: str,
        repository: str
    ) -> ActionableHint:
        """Generate hint for configuration failures"""
        return ActionableHint(
            message=f"Manually inspect and repair configuration in '{repository}'",
            suggested_commands=[
                f"cd {repository}",
                "cat .code-indexer/config.json",
                "cidx init --force"
            ],
            explanation="Configuration repair failed - manual intervention needed"
        )

    def _generic_hint(
        self,
        command: str,
        repository: str
    ) -> ActionableHint:
        """Generate generic hint when specific hint not available"""
        return ActionableHint(
            message=f"Navigate to '{repository}' and run command directly",
            suggested_commands=[
                f"cd {repository}",
                f"cidx {command}"
            ],
            explanation="Direct execution in repository context may provide more details"
        )
```

### 2. Hint Formatting
```python
class HintFormatter:
    """Format hints for display"""

    def format_hint(self, hint: ActionableHint) -> str:
        """
        Format hint with commands and explanation.

        Output format:
        Hint: Use grep or other search tools to search 'backend/auth-service' manually

        Try these commands:
          • grep -r 'your-search-term' backend/auth-service
          • rg 'your-search-term' backend/auth-service
          • cd backend/auth-service && cidx status

        Explanation: Qdrant service not available - alternative search methods can still find code
        """
        lines = [f"Hint: {hint.message}"]

        if hint.suggested_commands:
            lines.append("\nTry these commands:")
            for cmd in hint.suggested_commands:
                lines.append(f"  • {cmd}")

        if hint.explanation:
            lines.append(f"\nExplanation: {hint.explanation}")

        return '\n'.join(lines)
```

### 3. Context-Aware Hint Selection
```python
class ContextAwareHintSelector:
    """Select most appropriate hint based on full context"""

    def __init__(self):
        self.generator = HintGenerator()

    def select_hint(
        self,
        command: str,
        error_text: str,
        repository: str,
        exit_code: int
    ) -> ActionableHint:
        """
        Select most appropriate hint based on all available context.

        Considers:
        - Command type
        - Error message content
        - Exit code
        - Repository state
        """
        # Generate base hint
        hint = self.generator.generate_hint(command, error_text, repository)

        # Enhance hint based on exit code
        if exit_code == 127:
            # Command not found
            hint.message = "CIDX command not found in PATH"
            hint.suggested_commands = [
                "which cidx",
                "echo $PATH",
                "pip install code-indexer"
            ]

        return hint
```

### 4. Error Category Detection
```python
class ErrorCategoryDetector:
    """Detect error category from error message"""

    ERROR_PATTERNS = {
        'connection': [
            r'cannot connect',
            r'connection refused',
            r'no.*service.*found',
            r'qdrant.*not.*running'
        ],
        'port_conflict': [
            r'port.*already in use',
            r'address already in use',
            r'bind.*failed'
        ],
        'permission': [
            r'permission denied',
            r'access denied',
            r'forbidden'
        ],
        'configuration': [
            r'invalid.*config',
            r'missing.*config',
            r'config.*error'
        ],
        'timeout': [
            r'timeout',
            r'timed out',
            r'deadline exceeded'
        ]
    }

    def detect_category(self, error_text: str) -> str:
        """Detect error category from error message"""
        import re

        error_lower = error_text.lower()

        for category, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_lower):
                    return category

        return 'unknown'
```

## Testing Scenarios

### Unit Tests
1. **Test query failure hints**
   ```python
   hint = generator.generate_hint(
       command='query',
       error_text='Cannot connect to Qdrant',
       repository='backend/auth'
   )
   assert 'grep' in hint.message
   assert any('grep -r' in cmd for cmd in hint.suggested_commands)
   ```

2. **Test container failure hints**
   ```python
   hint = generator.generate_hint(
       command='start',
       error_text='Port 6333 already in use',
       repository='backend/auth'
   )
   assert 'port' in hint.message.lower()
   assert any('docker ps' in cmd for cmd in hint.suggested_commands)
   ```

3. **Test hint specificity**
   - Different commands get different hints
   - Same command with different errors get appropriate hints
   - Hints are actionable and specific

### Integration Tests
1. **Test hint display in error messages**
   ```bash
   # Cause query failure by stopping service
   cd repo1 && cidx stop && cd ..

   # Execute proxy query
   cidx query "test"

   # Verify hint appears in error output
   # Should suggest grep as alternative
   ```

2. **Test hint appropriateness**
   - Verify hints match error type
   - Check suggested commands are valid
   - Confirm hints are helpful

## Error Handling

### Hint Generation Failures
- Always provide fallback hint
- Never crash on hint generation error
- Log hint generation issues
- Provide generic guidance if specific hint fails

## Performance Considerations
- Hint generation should be fast (<10ms)
- Pre-compile regex patterns
- Cache common hints
- Minimal string processing

## Dependencies
- `re` for pattern matching
- `typing` for type hints
- `dataclasses` for hint structure
- No external dependencies

## Documentation Updates
- Document hint generation logic
- List all error categories
- Provide hint examples
- Explain customization options

## Example Hints

### Query Failure (Connection Error)
```
Hint: Use grep or other search tools to search 'backend/auth-service' manually

Try these commands:
  • grep -r 'authentication' backend/auth-service
  • rg 'authentication' backend/auth-service
  • cd backend/auth-service && cidx status

Explanation: Qdrant service not available - alternative search methods can still find code
```

### Container Start Failure (Port Conflict)
```
Hint: Check for port conflicts with existing containers

Try these commands:
  • docker ps
  • podman ps
  • cd backend/auth-service && cidx status
  • cd backend/auth-service && cidx fix-config

Explanation: Port already in use - need to resolve conflict
```

### Status Check Failure
```
Hint: Navigate to 'backend/auth-service' to investigate configuration

Try these commands:
  • cd backend/auth-service
  • cidx fix-config
  • cidx start

Explanation: Status check failed - may need configuration repair
```

### Configuration Error
```
Hint: Manually inspect and repair configuration in 'backend/auth-service'

Try these commands:
  • cd backend/auth-service
  • cat .code-indexer/config.json
  • cidx init --force

Explanation: Configuration repair failed - manual intervention needed
```

## User Experience Principles
- Every error should have actionable guidance
- Hints should be command-specific
- Suggest concrete next steps
- Provide alternative approaches
- Enable self-service problem resolution

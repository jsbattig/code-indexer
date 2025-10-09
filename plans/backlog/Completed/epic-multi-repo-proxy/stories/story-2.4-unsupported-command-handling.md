# Story: Unsupported Command Handling

## Story ID: STORY-2.4
## Feature: FEAT-002 (Command Forwarding Engine)
## Priority: P0 - Must Have
## Size: Small

## User Story
**As a** developer using proxy mode
**I want to** receive clear error messages for unsupported commands
**So that** I understand which operations aren't available in proxy mode

## Conversation Context
**Citation**: "Any other command that is not supported, it should error out with a clear message."

**Citation**: "this is not ncesary: 'proxied_commands': [...]. Those are the proxied commands, period. Hard coded."

**Context**: The conversation established a hardcoded list of supported proxy commands (query, status, start, stop, uninstall, fix-config, watch). Any command not in this list should produce a clear, actionable error message directing users to execute the command in the specific repository.

## Acceptance Criteria
- [ ] `init` in proxy mode shows clear error message
- [ ] `index` in proxy mode shows clear error message
- [ ] Error message states command not supported in proxy mode
- [ ] Error message suggests navigating to specific repository
- [ ] Exit code is 3 (invalid command/configuration)
- [ ] Error includes list of supported commands
- [ ] No subprocess execution attempted for unsupported commands

## Technical Implementation

### 1. Command Validation
```python
# proxy/command_validator.py
from typing import Set

# Hardcoded supported commands (as per conversation)
PROXIED_COMMANDS: Set[str] = {
    'query',
    'status',
    'start',
    'stop',
    'uninstall',
    'fix-config',
    'watch'
}

class UnsupportedProxyCommandError(Exception):
    """Raised when unsupported command attempted in proxy mode"""

    def __init__(self, command: str):
        self.command = command
        self.message = self._generate_error_message(command)
        super().__init__(self.message)

    def _generate_error_message(self, command: str) -> str:
        """Generate helpful error message"""
        return f"""
ERROR: Command '{command}' is not supported in proxy mode.

The following commands can be used in proxy mode:
  - query      : Search across all repositories
  - status     : Check status of all repositories
  - start      : Start services in all repositories
  - stop       : Stop services in all repositories
  - uninstall  : Uninstall services from all repositories
  - fix-config : Fix configuration in all repositories
  - watch      : Watch for changes in all repositories

To run '{command}', navigate to a specific repository:
  cd <repository-path>
  cidx {command}
"""

def validate_proxy_command(command: str) -> None:
    """
    Validate that command is supported in proxy mode.

    Raises:
        UnsupportedProxyCommandError: If command not supported
    """
    if command not in PROXIED_COMMANDS:
        raise UnsupportedProxyCommandError(command)

def is_supported_proxy_command(command: str) -> bool:
    """Check if command is supported in proxy mode"""
    return command in PROXIED_COMMANDS
```

### 2. Early Command Interception
```python
# cli/command_wrapper.py
class CommandWrapper:
    """Wraps commands to handle proxy mode detection and validation"""

    def execute(self, command: str, *args, **kwargs):
        """Execute command with proxy validation"""
        config_path, mode = ConfigManager.detect_mode()

        if mode == 'proxy':
            # Validate command BEFORE any execution
            try:
                validate_proxy_command(command)
            except UnsupportedProxyCommandError as e:
                print(e.message, file=sys.stderr)
                sys.exit(3)  # Exit code 3: Invalid command

            # Command is supported, proceed with proxy execution
            return self._execute_proxy_mode(config_path, command, *args, **kwargs)
        else:
            # Regular mode - all commands supported
            return self._execute_regular_mode(command, *args, **kwargs)
```

### 3. Error Message Formatting
```python
class ErrorMessageFormatter:
    """Format error messages for unsupported commands"""

    @staticmethod
    def format_unsupported_command(
        command: str,
        supported_commands: Set[str]
    ) -> str:
        """Format error message with helpful guidance"""
        lines = [
            f"ERROR: Command '{command}' is not supported in proxy mode.\n",
            "Supported proxy commands:",
        ]

        # Add each supported command with description
        command_descriptions = {
            'query': 'Search across all repositories',
            'status': 'Check status of all repositories',
            'start': 'Start services in all repositories',
            'stop': 'Stop services in all repositories',
            'uninstall': 'Uninstall services from all repositories',
            'fix-config': 'Fix configuration in all repositories',
            'watch': 'Watch for changes in all repositories'
        }

        for cmd in sorted(supported_commands):
            desc = command_descriptions.get(cmd, '')
            lines.append(f"  • {cmd:12} - {desc}")

        lines.extend([
            "",
            f"To run '{command}', navigate to a specific repository:",
            "  cd <repository-path>",
            f"  cidx {command}"
        ])

        return '\n'.join(lines)
```

### 4. Exit Code Handling
```python
# Exit code constants
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_PARTIAL_SUCCESS = 2
EXIT_INVALID_COMMAND = 3

def handle_unsupported_command(command: str) -> int:
    """
    Handle unsupported command in proxy mode.

    Returns:
        Exit code 3 for invalid command
    """
    error_msg = ErrorMessageFormatter.format_unsupported_command(
        command,
        PROXIED_COMMANDS
    )
    print(error_msg, file=sys.stderr)
    return EXIT_INVALID_COMMAND
```

### 5. Command Suggestions
```python
def suggest_alternative(command: str) -> str:
    """Suggest alternative approaches for unsupported commands"""
    suggestions = {
        'init': "Initialize each repository individually by navigating to it",
        'index': "Index each repository individually by navigating to it",
        'reconcile': "Reconcile specific repositories individually",
    }

    suggestion = suggestions.get(command)
    if suggestion:
        return f"\nSuggestion: {suggestion}"
    return ""
```

## Testing Scenarios

### Unit Tests
1. **Test command validation**
   ```python
   # Supported commands should pass
   assert is_supported_proxy_command('query') == True
   assert is_supported_proxy_command('status') == True

   # Unsupported commands should fail
   assert is_supported_proxy_command('init') == False
   assert is_supported_proxy_command('index') == False
   ```

2. **Test error message generation**
   - Verify error message contains command name
   - Check supported commands listed
   - Verify navigation instructions included

3. **Test exit code**
   - Unsupported command returns exit code 3
   - Supported commands don't trigger error path
   - Error message written to stderr

### Integration Tests
1. **Test unsupported command execution**
   ```bash
   # Setup proxy mode
   cd test-proxy
   cidx init --proxy-mode

   # Try unsupported commands
   cidx init
   # Should error with message and exit code 3

   cidx index
   # Should error with message and exit code 3
   ```

2. **Test error message content**
   - Parse error output
   - Verify all supported commands listed
   - Check navigation instructions present
   - Verify exit code is 3

3. **Test no subprocess execution**
   - Mock subprocess.run
   - Execute unsupported command
   - Verify no subprocess calls made
   - Confirm early validation prevents execution

## Error Handling

### Error Message Display
1. **Clear Command Identification**
   - Message includes attempted command name
   - Easy to scan and understand
   - Immediately actionable

2. **Comprehensive Guidance**
   - List all supported commands
   - Explain what each command does
   - Show how to use unsupported command
   - Include concrete example

3. **Exit Code Semantics**
   - 0: Complete success
   - 1: Complete failure
   - 2: Partial success
   - 3: Invalid command/configuration

## Dependencies
- `typing` for type hints
- `sys` for stderr and exit codes
- Existing ConfigManager for mode detection
- No subprocess execution for validation

## Security Considerations
- Validate command names before processing
- Prevent command injection attempts
- No execution of unvalidated commands
- Safe error message generation

## Documentation Updates
- Document supported proxy commands
- Explain why certain commands not supported
- Provide examples of error messages
- Include troubleshooting guide

## Example Error Messages

### Init Command in Proxy Mode
```bash
$ cidx init

ERROR: Command 'init' is not supported in proxy mode.

Supported proxy commands:
  • fix-config  - Fix configuration in all repositories
  • query       - Search across all repositories
  • start       - Start services in all repositories
  • status      - Check status of all repositories
  • stop        - Stop services in all repositories
  • uninstall   - Uninstall services from all repositories
  • watch       - Watch for changes in all repositories

To run 'init', navigate to a specific repository:
  cd <repository-path>
  cidx init
```

### Index Command in Proxy Mode
```bash
$ cidx index

ERROR: Command 'index' is not supported in proxy mode.

Supported proxy commands:
  • fix-config  - Fix configuration in all repositories
  • query       - Search across all repositories
  • start       - Start services in all repositories
  • status      - Check status of all repositories
  • stop        - Stop services in all repositories
  • uninstall   - Uninstall services from all repositories
  • watch       - Watch for changes in all repositories

To run 'index', navigate to a specific repository:
  cd <repository-path>
  cidx index
```

## Performance Considerations
- Validation happens before any subprocess execution
- No performance penalty for early error detection
- Error message generation is fast
- No network or disk I/O for validation

## User Experience
- Errors are impossible to miss
- Guidance is immediately actionable
- No confusion about what went wrong
- Clear path forward for user

# Feature: Command Forwarding Engine

## Feature ID: FEAT-002
## Epic: EPIC-001 (Multi-Repository Proxy Configuration Support)
## Status: Specification
## Priority: P0 (Core Infrastructure)

## Overview

Implement the core command forwarding mechanism that routes CIDX commands to multiple repositories based on proxy configuration. This feature handles command execution strategies (parallel vs sequential) and manages subprocess lifecycle.

## User Stories

### Story 2.1: Automatic Proxy Mode Detection
**As a** developer working in a proxy-managed directory
**I want to** have commands automatically detect proxy mode
**So that** I don't need special flags for every command

### Story 2.2: Parallel Command Execution
**As a** developer querying multiple repositories
**I want to** have read-only commands execute in parallel
**So that** I get faster results across all projects

### Story 2.3: Sequential Command Execution
**As a** developer managing container lifecycle
**I want to** have resource-intensive commands execute sequentially
**So that** I avoid resource contention and race conditions

### Story 2.4: Unsupported Command Handling
**As a** developer using proxy mode
**I want to** receive clear error messages for unsupported commands
**So that** I understand which operations aren't available in proxy mode

## Technical Requirements

### Proxy Mode Detection
- Walk up directory tree to find `.code-indexer/` configuration
- Check for `"proxy_mode": true` in configuration
- Activate proxy forwarding automatically when detected
- No special command-line flags required

**Citation**: "Auto detect. In fact, you apply the same topmost .code-indexer folder found logic we use for other commands (as git)."

### Supported Commands (Hardcoded)
```python
PROXIED_COMMANDS = [
    'query', 'status', 'start', 'stop',
    'uninstall', 'fix-config', 'watch'
]
```
**Citation**: "this is not ncesary: 'proxied_commands': [...]. Those are the proxied commands, period. Hard coded."

### Execution Strategy (Hardcoded)
```python
PARALLEL_COMMANDS = ['query', 'status', 'watch', 'fix-config']
SEQUENTIAL_COMMANDS = ['start', 'stop', 'uninstall']
```
**Citation**: "Parallel for all, except start, stop and uninstall to prevent potential resource spikes and resource contention or race conditions."

### Command Routing Logic
1. Detect if current directory is under proxy management
2. Check if command is in supported list
3. Determine execution strategy (parallel/sequential)
4. Forward command to each configured repository
5. Collect and format outputs appropriately

### Unsupported Commands
- Commands like `init`, `index` should error with clear message
- **Citation**: "Any other command that is not supported, it should error out with a clear message."

## Acceptance Criteria

### Story 2.1: Automatic Detection
- [ ] Commands detect proxy mode without `--proxy` flag
- [ ] Detection uses same upward search as other CIDX commands
- [ ] Proxy mode activates only when `"proxy_mode": true` found
- [ ] Regular mode continues when no proxy configuration exists

### Story 2.2: Parallel Execution
- [ ] `query` command executes simultaneously across repositories
- [ ] `status` command runs in parallel for all repos
- [ ] `watch` command spawns parallel processes
- [ ] `fix-config` executes concurrently
- [ ] Results are collected from all parallel executions

### Story 2.3: Sequential Execution
- [ ] `start` command processes repositories one at a time
- [ ] `stop` command executes sequentially
- [ ] `uninstall` runs one repository at a time
- [ ] Each command completes before next begins
- [ ] Order follows configuration list sequence

### Story 2.4: Unsupported Commands
- [ ] `init` in proxy mode shows error message
- [ ] `index` in proxy mode shows error message
- [ ] Error message clearly states command not supported in proxy mode
- [ ] Error message suggests navigating to specific repository

## Implementation Notes

### Command Executor Architecture
```python
class ProxyCommandExecutor:
    def execute(self, command: str, args: List[str]):
        if command not in PROXIED_COMMANDS:
            raise UnsupportedProxyCommand(command)

        strategy = self._get_execution_strategy(command)
        repos = self._load_repository_list()

        if strategy == 'parallel':
            return self._execute_parallel(command, args, repos)
        else:
            return self._execute_sequential(command, args, repos)
```

### Subprocess Management
- Use subprocess.run() for command execution
- Capture stdout and stderr separately
- Handle process termination gracefully
- Propagate Ctrl-C to child processes

### Output Collection
- Maintain repository order for sequential commands
- Collect outputs as they complete for parallel commands
- Preserve exit codes from each repository
- Track which repositories succeeded/failed

## Dependencies
- ConfigManager for proxy configuration loading
- Subprocess module for command execution
- Threading/asyncio for parallel execution
- Existing CLI command structure

## Testing Requirements

### Unit Tests
- Proxy mode detection logic
- Command classification (proxied/non-proxied)
- Execution strategy selection
- Error handling for unsupported commands

### Integration Tests
- Parallel command execution with multiple repos
- Sequential command execution order
- Output collection and formatting
- Process termination handling
- Ctrl-C signal propagation

## Performance Considerations

### Parallel Execution
- Thread pool size should be reasonable (e.g., min(repo_count, 10))
- Avoid overwhelming system with too many concurrent processes
- Consider memory usage when collecting outputs

### Sequential Execution
- Provide progress indication for long-running sequential commands
- Consider timeout mechanisms for hung processes
- Ensure clean process termination between repositories

## Error Handling

### Partial Failures
- Continue execution for other repositories on failure
- Collect and report all errors at the end
- Maintain clear association between errors and repositories
- **Citation**: "Partial success OK."

### Process Management
- Handle subprocess crashes gracefully
- Clean up zombie processes
- Propagate signals appropriately
- Timeout long-running commands if needed
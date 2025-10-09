# Epic: Multi-Repository Proxy Configuration Support

## Epic ID: EPIC-001
## Status: Specification
## Version: 1.0.0

## Executive Summary

Enable CIDX to operate in a proxy mode where commands executed at a root directory are automatically forwarded to multiple indexed sub-repositories. This allows users to perform operations (query, status, start, stop, etc.) across multiple projects simultaneously from a single command, with intelligent result aggregation for semantic queries.

## Business Value

### Problem Statement
Users working with multiple related repositories (microservices, monorepos with separate indexing, test environments) must currently navigate to each repository individually to perform CIDX operations. This creates friction when searching for code across related projects or managing container lifecycle for multiple services.

### Solution
Introduce a proxy mode that allows CIDX to detect and operate on multiple indexed repositories from a parent directory, forwarding supported commands and aggregating results intelligently.

### Key Benefits
- **Unified Search**: Query multiple repositories with a single command
- **Centralized Management**: Start/stop/monitor multiple project containers from one location
- **Developer Efficiency**: Reduce context switching between related projects
- **Flexible Organization**: Support various repository structures without enforcing rigid hierarchies

## Scope

### In Scope (V1)
1. Proxy mode initialization via `cidx init --proxy-mode`
2. Automatic discovery of indexed sub-repositories
3. Command forwarding for: `query`, `status`, `start`, `stop`, `uninstall`, `fix-config`, `watch`
4. Intelligent result aggregation for `query` command
5. Parallel/sequential execution strategies based on command type
6. Partial success model with clear error reporting
7. Auto-detection of proxy mode based on configuration

### Out of Scope (V1)
1. `index` command support (due to rich progress UI complexity)
   - **Citation**: "I'm on the fence in terms of supporting 'index' command, because it has rich logic to show on the screen, it will be hard to support that."
2. Nested proxy configurations
   - **Citation**: "Prohibit nesting for now."
3. Dynamic repository addition/removal (requires manual config editing)
4. Cross-repository deduplication of search results

## Technical Architecture

### Configuration Structure
```json
{
  "proxy_mode": true,
  "discovered_repos": [
    "project-a",
    "project-b",
    "tests/sample-repo"
  ]
}
```
**Citation**: "this is not ncesary: 'proxied_commands': [...]. Those are the proxied commands, period. Hard coded."

### Command Execution Model

#### Hardcoded Proxy Commands
- **Proxied**: `query`, `status`, `start`, `stop`, `uninstall`, `fix-config`, `watch`
- **Non-proxied**: `--help` (executes normally)
- **Unsupported**: `init`, `index`, etc. (clear error message)

**Citation**: "Any other command that is not supported, it should error out with a clear message."

#### Execution Strategy (Hardcoded)
- **Parallel**: `query`, `status`, `watch`, `fix-config`
- **Sequential**: `start`, `stop`, `uninstall`

**Citation**: "Parallel for all, except start, stop and uninstall to prevent potential resource spikes and resource contention or race conditions."

### Discovery Mechanism
1. Walk up directory tree to find topmost `.code-indexer/` folder
2. Check for `"proxy_mode": true` in configuration
3. If proxy mode detected, activate command forwarding
4. No special flags needed for command execution

**Citation**: "Auto detect. In fact, you apply the same topmost .code-indexer folder found logic we use for other commands (as git). you will find our multi-repo folder, and use that one."

### Output Formatting Strategy

#### Standard Commands (`status`, `start`, `stop`, `uninstall`, `fix-config`, `watch`)
- Simple concatenation of outputs
- Display in repository order
- No formatting or tables

**Citation**: "No tabbles. You take the output from the commands, and you display one after another, in order. Nothing fancier than that."

#### Query Command (Special Handling)
- Parse individual repository results
- Extract matches with scores and paths
- Merge all matches into single list
- Sort by score (descending)
- Apply `--limit` to merged results
- Display interleaved results

**Citation**: "Interleaved by score I think it's better so we keep the order of most relevant results on top."

## Features Breakdown

### Feature 1: Proxy Mode Initialization
Enable creation and discovery of proxy configurations

### Feature 2: Command Forwarding Engine
Implement command routing and execution strategies

### Feature 3: Query Result Aggregation
Smart merging and sorting of semantic search results

### Feature 4: Error Handling and Partial Success
Graceful failure handling with actionable error messages

### Feature 5: Watch Command Multiplexing
Support for concurrent watch processes with unified output

## Success Criteria

1. `cidx init --proxy-mode` successfully creates proxy configuration
2. Commands execute across all configured repositories
3. Query results are properly merged and sorted by relevance
4. Partial failures don't block successful repository operations
5. Error messages clearly identify failed repositories
6. No performance regression for single-repository operations

## Implementation Priority

1. **Phase 1**: Core proxy infrastructure (Features 1, 2)
2. **Phase 2**: Query aggregation (Feature 3)
3. **Phase 3**: Error handling refinement (Feature 4)
4. **Phase 4**: Watch command support (Feature 5)

## Risk Mitigation

### Technical Risks
1. **Risk**: Command output interleaving causing confusion
   - **Mitigation**: Clear repository prefixes in output

2. **Risk**: Resource contention with parallel execution
   - **Mitigation**: Sequential execution for resource-intensive commands

3. **Risk**: Partial failures causing data inconsistency
   - **Mitigation**: Clear error reporting with manual intervention guidance

## Dependencies

- Existing CIDX command infrastructure
- ConfigManager for configuration discovery
- Command execution framework for subprocess management
- Query result parsing capabilities

## Acceptance Criteria

- [ ] Proxy mode can be initialized at any directory level
- [ ] Sub-repositories are automatically discovered during initialization
- [ ] All specified commands properly forward to sub-repositories
- [ ] Query results are merged and sorted by relevance score
- [ ] Errors in individual repositories don't crash the entire operation
- [ ] Configuration auto-detection works without special flags
- [ ] Nested proxy configurations are properly rejected
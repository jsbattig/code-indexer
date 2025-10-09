# Multi-Repository Proxy Configuration Support - Epic Documentation

## Overview
This directory contains the complete epic specification for implementing multi-repository proxy configuration support in CIDX. The feature enables executing CIDX commands across multiple indexed repositories from a single parent directory.

## Document Structure

### Epic Level
- **[epic-multi-repo-proxy.md](./epic-multi-repo-proxy.md)** - Main epic document with executive summary, business value, scope, and technical architecture

### Feature Level
Features represent major functional areas within the epic:

1. **[feature-01-proxy-initialization.md](./features/feature-01-proxy-initialization.md)** - Proxy mode initialization and repository discovery
2. **[feature-02-command-forwarding.md](./features/feature-02-command-forwarding.md)** - Command routing and execution strategies
3. **[feature-03-query-aggregation.md](./features/feature-03-query-aggregation.md)** - Intelligent semantic search result merging
4. **[feature-04-error-handling.md](./features/feature-04-error-handling.md)** - Partial success model and error reporting
5. **[feature-05-watch-multiplexing.md](./features/feature-05-watch-multiplexing.md)** - Multi-repository watch mode support

### Story Level
Stories provide detailed implementation specifications:

1. **[story-1.1-initialize-proxy-mode.md](./stories/story-1.1-initialize-proxy-mode.md)** - Detailed implementation of `cidx init --proxy-mode`
2. **[story-2.1-proxy-detection.md](./stories/story-2.1-proxy-detection.md)** - Automatic proxy mode detection logic
3. **[story-3.1-query-result-parser.md](./stories/story-3.1-query-result-parser.md)** - Query output parsing and result extraction

### Implementation Guide
- **[implementation-order.md](./implementation-order.md)** - Phased implementation plan with dependencies and success metrics

## Key Requirements from Conversation

All specifications are directly derived from conversation requirements with specific citations:

### Core Functionality
- **Proxy initialization**: `cidx init --proxy-mode` creates proxy configuration
- **Auto-discovery**: Automatically finds all `.code-indexer/` subdirectories
- **Auto-detection**: Commands automatically detect proxy mode (no special flags)
- **Command support**: Hardcoded list of proxied commands (query, status, start, stop, etc.)
- **Execution strategy**: Parallel for most commands, sequential for resource-intensive ones

### Technical Decisions
- **No config for commands**: Proxied commands are hardcoded, not configurable
- **No config for strategy**: Parallel/sequential execution is hardcoded
- **Relative paths only**: Store relative paths in configuration
- **No nested proxies**: Prohibited in V1 for simplicity
- **No index command**: Not supported due to rich UI complexity

### Output Behavior
- **Standard commands**: Simple concatenation of outputs
- **Query command**: Parse, merge, sort by score, apply global limit
- **Error handling**: Partial success with clear error messages and hints

## Quick Reference

### Supported Commands (Hardcoded)
```python
PROXIED_COMMANDS = ['query', 'status', 'start', 'stop', 'uninstall', 'fix-config', 'watch']
PARALLEL_EXECUTION = ['query', 'status', 'watch', 'fix-config']
SEQUENTIAL_EXECUTION = ['start', 'stop', 'uninstall']
```

### Configuration Structure
```json
{
  "proxy_mode": true,
  "discovered_repos": [
    "backend/auth-service",
    "backend/user-service",
    "frontend/web-app"
  ]
}
```

### Usage Examples
```bash
# Initialize proxy mode
cidx init --proxy-mode

# Commands work automatically from any subdirectory
cidx query "authentication"  # Searches all repositories
cidx status                   # Shows status for all repositories
cidx start                    # Starts services sequentially
```

## Implementation Status
- [ ] Phase 1: Core Infrastructure
- [ ] Phase 2: Command Forwarding
- [ ] Phase 3: Query Intelligence
- [ ] Phase 4: Error Handling
- [ ] Phase 5: Watch Support

## Related Documentation
- Main CIDX documentation: `/README.md`
- Architecture documentation: `/docs/architecture/`
- Testing documentation: `/docs/testing/`

## Contact
For questions about this epic specification, please refer to the conversation context citations included throughout the documents.
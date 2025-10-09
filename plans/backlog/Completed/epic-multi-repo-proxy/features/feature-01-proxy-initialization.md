# Feature: Proxy Mode Initialization

## Feature ID: FEAT-001
## Epic: EPIC-001 (Multi-Repository Proxy Configuration Support)
## Status: Specification
## Priority: P0 (Core Infrastructure)

## Overview

Implement the ability to initialize a directory as a proxy configuration point that manages multiple indexed sub-repositories. This feature establishes the foundation for multi-repository operations.

## User Stories

### Story 1.1: Initialize Proxy Mode
**As a** developer working with multiple repositories
**I want to** initialize a parent directory as a proxy configuration
**So that** I can manage multiple indexed projects from a single location

### Story 1.2: Auto-Discovery of Sub-Repositories
**As a** developer initializing proxy mode
**I want to** automatically discover all indexed sub-repositories
**So that** I don't have to manually configure each repository path

### Story 1.3: Proxy Configuration Management
**As a** developer using proxy mode
**I want to** view and edit the list of managed repositories
**So that** I can customize which projects are included in proxy operations

### Story 1.4: Nested Proxy Prevention
**As a** system administrator
**I want to** prevent creation of nested proxy configurations
**So that** the system maintains predictable behavior and avoids complexity

## Technical Requirements

### Initialization Command
```bash
cidx init --proxy-mode
```
**Citation**: "I was thinking we do 'init' --proxy-down to initialize it as a proxy folder."

### Configuration Structure
- Create `.code-indexer/` directory at proxy root
- Generate proxy-specific configuration file
- Auto-discover and list sub-repositories with `.code-indexer/` configs
- Store relative paths only

**Citation**: "you create the .code-indexer folder, as we do with others, and you create the config file"

### Discovery Rules
- Scan immediate subdirectories and nested paths
- Check for `.code-indexer/` directory existence only
- Do NOT validate configuration validity
- Do NOT copy ports or other configuration details

**Citation**: "Check for existence only."
**Citation**: "The only thing our proxy needs to know is the subfolder with config, that's it, don't copy ports or an other info."

### Regular Init Behavior
- Standard `cidx init` (without `--proxy-mode`) continues to work normally
- Allow nested indexed folders for legitimate use cases
- No validation to prevent nested repositories in regular mode

**Citation**: "there may be legit reasons for this... like this folder! you may create a subfolder to test somethjing"

## Acceptance Criteria

### Story 1.1: Initialize Proxy Mode
- [ ] Command `cidx init --proxy-mode` creates `.code-indexer/` directory
- [ ] Configuration file contains `"proxy_mode": true`
- [ ] Configuration structure matches server mode patterns
- [ ] Command fails gracefully if already initialized
- [ ] Command rejects nested proxy creation

### Story 1.2: Auto-Discovery
- [ ] Discovery scans all subdirectories recursively
- [ ] Identifies folders containing `.code-indexer/` directory
- [ ] Stores discovered paths in configuration
- [ ] Uses relative paths from proxy root
- [ ] Discovery runs during initialization only

### Story 1.3: Configuration Management
- [ ] Configuration file is human-readable JSON
- [ ] Repository list can be manually edited
- [ ] Relative paths are preserved in configuration
- [ ] Configuration changes take effect immediately

### Story 1.4: Nested Proxy Prevention
- [ ] Initialization fails if parent directory has proxy configuration
- [ ] Clear error message explains the restriction
- [ ] Regular (non-proxy) initialization still allowed within proxy-managed folders

## Implementation Notes

### Configuration File Example
```json
{
  "proxy_mode": true,
  "discovered_repos": [
    "backend/auth-service",
    "backend/user-service",
    "frontend/web-app",
    "tests/integration"
  ]
}
```

### Path Storage
- Use relative paths exclusively
- **Citation**: "RElative path"

### Validation Scope
- Only check for directory existence
- No configuration validation
- No port or service validation
- **Citation**: "Check for existence only."

## Dependencies
- ConfigManager for configuration creation
- File system utilities for directory scanning
- Existing init command infrastructure

## Testing Requirements

### Unit Tests
- Proxy mode flag parsing
- Configuration file creation
- Directory discovery logic
- Nested proxy detection

### Integration Tests
- Full initialization workflow
- Discovery with various directory structures
- Configuration persistence and loading
- Error handling for edge cases

## Performance Considerations
- Directory scanning should be optimized for large folder structures
- Discovery is one-time operation during initialization
- No runtime performance impact after configuration
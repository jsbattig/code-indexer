# Epic: Server Composite Repository Activation

## Epic Overview
Enable the CIDX server to activate and query composite repositories (multiple golden repos as one), matching the CLI's proxy mode capabilities introduced in v6.0.0.

## Business Value
**Problem Statement**: "CLI now supports multi-repository proxy mode (v6.0.0), but the CIDX server only activates single golden repositories. This creates a capability gap between CLI and server." [Phase 1]

**Target Users**: "Developers and agentic developer entities" [Phase 1]

**Success Criteria**: "You can activate a composite repo and run a query, which returns a multi-repo result correctly" [Phase 1]

**Business Impact**: "make sure it works, and we will get value" [Phase 1]

## Technical Scope

### Supported Operations (from CLI proxy mode)
✅ **Fully Supported**: query, status, start, stop, uninstall, fix-config, watch [Phase 4]
❌ **Not Supported**: init, index, reconcile, branch operations, sync [Phase 4, Phase 5]

### Implementation Strategy
**Maximum CLI Reuse Mandate**: "reuse EVERYTHING you can, already implemented in the context of the CLI under the hood classes, and don't re-implement in the server context" [Phase 6]

**Total New Code**: ~200 lines of server extensions that wrap existing CLI components

## Features

### Feature 1: Composite Repository Activation
Enable activation of multiple golden repositories as a single composite activated repository.

**User Story**: "User activated a composite repo before starting a coding task, and keeps it activated during it's activity" [Phase 2]

### Feature 2: Multi-Repository Query Execution
Execute semantic queries across all component repositories with proper result aggregation.

**Acceptance Criteria**: "ultimate acceptance criteria is that you can activate a repo, and run queries on it and you confirm matches from multiple underlying repos are coming back, in the right order" [Phase 3]

### Feature 3: Composite Repository Management
Manage composite repository lifecycle and handle unsupported operations gracefully.

**Constraints**: "Commands limited to what's already supported within cidx for composite repos" [Phase 1]

## Implementation Phases

### Phase 1: Core Activation (Feature 1)
- Extend activation API to accept golden repository arrays
- Create composite filesystem structure using ProxyInitializer
- Implement metadata and state management

### Phase 2: Query Execution (Feature 2)
- Implement query routing and composite detection
- Integrate CLI's _execute_query() for parallel execution
- Ensure proper result ordering and aggregation

### Phase 3: Management Operations (Feature 3)
- Block unsupported operations with appropriate 400 errors
- Implement repository details aggregation
- Support file listing and deactivation

## Constraints and Decisions

### Architectural Decisions
- **Branch Operations**: "Branch Switch, Branch List and Sync I'm ok with 400" [Phase 5]
- **Repository Details**: "let's return the info of all subrepos" [Phase 5]
- **File Listing**: "why can't we support it? it's a folder.... why can't you list all files?" [Phase 5]

### Technical Constraints
- Reuse ProxyInitializer, ProxyConfigManager, QueryResultAggregator from CLI
- No reimplementation of existing CLI functionality
- Maintain compatibility with existing single-repo activation

## Success Metrics
- Composite repository activation completes successfully
- Queries return results from all component repositories
- Results are properly ordered by global relevance score
- Unsupported operations return clear 400 error messages
- All existing single-repo functionality remains unchanged

## Risk Mitigation
- **Edge Case**: "Commands supported in the API that are not supported for composite repos at the CLI level" [Phase 3] - Return 400 with clear guidance
- **Testing**: Verify parallel query execution matches CLI behavior exactly
- **Backward Compatibility**: Ensure single-repo activation continues to work

## Dependencies
- CLI proxy mode implementation (v6.0.0)
- Existing ProxyInitializer and ProxyConfigManager classes
- cli_integration._execute_query() function
- QueryResultAggregator for result merging
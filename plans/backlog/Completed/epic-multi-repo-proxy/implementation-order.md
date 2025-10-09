# Implementation Order: Multi-Repository Proxy Configuration Support

## Overview
This document defines the implementation sequence for the Multi-Repository Proxy Configuration epic, considering dependencies, risk mitigation, and incremental value delivery.

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
**Goal**: Establish foundation for proxy mode operations

#### 1.1 Story: Initialize Proxy Mode (STORY-1.1)
- **Priority**: P0 - Foundational
- **Dependencies**: None
- **Deliverables**:
  - `cidx init --proxy-mode` command
  - Configuration structure with `"proxy_mode": true`
  - Repository discovery mechanism
  - Nested proxy prevention

**Citation**: "I was thinking we do 'init' --proxy-down to initialize it as a proxy folder"

#### 1.2 Story: Automatic Proxy Mode Detection (STORY-2.1)
- **Priority**: P0 - Foundational
- **Dependencies**: STORY-1.1 (proxy config exists)
- **Deliverables**:
  - Upward directory tree search
  - Configuration mode detection
  - Auto-activation without flags

**Citation**: "Auto detect. In fact, you apply the same topmost .code-indexer folder found logic"

### Phase 2: Command Forwarding (Week 2)
**Goal**: Enable basic command execution across repositories

#### 2.1 Story: Command Classification and Routing (STORY-2.2)
- **Priority**: P0 - Core Functionality
- **Dependencies**: STORY-2.1 (detection works)
- **Deliverables**:
  - Hardcoded command lists (proxied/non-proxied)
  - Command router implementation
  - Unsupported command error handling

**Citation**: "Those are the proxied commands, period. Hard coded."

#### 2.2 Story: Parallel Command Execution (STORY-2.3)
- **Priority**: P0 - Core Functionality
- **Dependencies**: STORY-2.2 (routing works)
- **Deliverables**:
  - Parallel execution for: `query`, `status`, `watch`, `fix-config`
  - Subprocess management
  - Output collection

**Citation**: "Parallel for all, except start, stop and uninstall"

#### 2.3 Story: Sequential Command Execution (STORY-2.4)
- **Priority**: P0 - Core Functionality
- **Dependencies**: STORY-2.2 (routing works)
- **Deliverables**:
  - Sequential execution for: `start`, `stop`, `uninstall`
  - Order preservation
  - Resource contention prevention

### Phase 3: Query Intelligence (Week 3)
**Goal**: Implement smart aggregation for semantic search

#### 3.1 Story: Query Result Parser (STORY-3.1)
- **Priority**: P0 - Critical Feature
- **Dependencies**: STORY-2.3 (parallel execution)
- **Deliverables**:
  - Output format detection
  - Result extraction (score, path, context)
  - Repository association

#### 3.2 Story: Result Aggregation and Sorting (STORY-3.2)
- **Priority**: P0 - Critical Feature
- **Dependencies**: STORY-3.1 (parsing works)
- **Deliverables**:
  - Multi-repository result merging
  - Score-based sorting
  - Global limit application

**Citation**: "Interleaved by score I think it's better so we keep the order of most relevant results on top"

#### 3.3 Story: Query Output Formatting (STORY-3.3)
- **Priority**: P1 - User Experience
- **Dependencies**: STORY-3.2 (aggregation works)
- **Deliverables**:
  - Repository-qualified paths
  - Consistent formatting
  - Clear result presentation

### Phase 4: Error Handling and Resilience (Week 4)
**Goal**: Ensure robust partial success semantics

#### 4.1 Story: Partial Success Model (STORY-4.1)
- **Priority**: P1 - Reliability
- **Dependencies**: Phase 2 complete
- **Deliverables**:
  - Continue on failure logic
  - Error collection
  - Success tracking

**Citation**: "Partial success OK"

#### 4.2 Story: Error Reporting and Hints (STORY-4.2)
- **Priority**: P1 - User Experience
- **Dependencies**: STORY-4.1
- **Deliverables**:
  - Clear error messages
  - Repository identification
  - Actionable hints (grep fallback)

**Citation**: "clearly stating so and hinting claude code to use grep or other means"

### Phase 5: Watch Command Support (Week 5)
**Goal**: Enable multi-repository monitoring

#### 5.1 Story: Watch Process Multiplexing (STORY-5.1)
- **Priority**: P2 - Enhancement
- **Dependencies**: STORY-2.3 (parallel execution)
- **Deliverables**:
  - Multiple watch process spawning
  - Output stream multiplexing
  - Repository prefixing

**Citation**: "multiple into single stdout"

#### 5.2 Story: Signal Propagation (STORY-5.2)
- **Priority**: P2 - Enhancement
- **Dependencies**: STORY-5.1
- **Deliverables**:
  - Ctrl-C handling
  - Clean process termination
  - No orphaned processes

**Citation**: "Ctrl-C propagates to all child processes"

## Testing Strategy

### Unit Testing (Continuous)
- Each story includes comprehensive unit tests
- Mock subprocess calls for command forwarding
- Test parsers with various output formats

### Integration Testing (End of each phase)
- Phase 1: Full initialization workflow
- Phase 2: Command execution across multiple repos
- Phase 3: End-to-end query aggregation
- Phase 4: Failure scenarios and recovery
- Phase 5: Watch mode with signal handling

### System Testing (Final week)
- Complete proxy mode workflows
- Performance testing with many repositories
- Stress testing with large outputs
- User acceptance testing

## Risk Mitigation

### Technical Risks
1. **Output parsing complexity**
   - Mitigation: Multiple fallback strategies
   - Implement robust parser early (Phase 3)

2. **Process management complexity**
   - Mitigation: Use proven subprocess patterns
   - Extensive testing of signal handling

3. **Performance with many repositories**
   - Mitigation: Implement parallel execution early
   - Add performance tests in Phase 2

### Schedule Risks
1. **Query parsing more complex than expected**
   - Mitigation: Start with simple formats, enhance incrementally
   - Have emergency parser as fallback

2. **Platform-specific issues (Windows/Linux/Mac)**
   - Mitigation: Test on all platforms early
   - Use cross-platform subprocess libraries

## Success Metrics

### Phase 1 Complete
- [ ] Proxy mode can be initialized
- [ ] Repositories are discovered automatically
- [ ] Configuration structure is correct

### Phase 2 Complete
- [ ] Commands execute on all repositories
- [ ] Parallel/sequential execution works correctly
- [ ] Unsupported commands show clear errors

### Phase 3 Complete
- [ ] Query results are properly aggregated
- [ ] Results sorted by relevance
- [ ] Limit applied correctly

### Phase 4 Complete
- [ ] Partial failures handled gracefully
- [ ] Clear error messages with hints
- [ ] No silent failures

### Phase 5 Complete
- [ ] Watch mode works across repositories
- [ ] Clean signal handling
- [ ] No process leaks

## Definition of Done
- [ ] All unit tests passing
- [ ] Integration tests passing
- [ ] Documentation updated
- [ ] Code reviewed and approved
- [ ] Performance benchmarks met
- [ ] No regressions in existing functionality

## Future Enhancements (Out of Scope V1)
1. Dynamic repository addition/removal
2. Cross-repository deduplication
3. Index command support (rich UI complexity)
4. Nested proxy configurations
5. Repository-specific command options
6. Proxy configuration UI/wizard

**Citation**: "I'm on the fence in terms of supporting 'index' command, because it has rich logic to show on the screen"
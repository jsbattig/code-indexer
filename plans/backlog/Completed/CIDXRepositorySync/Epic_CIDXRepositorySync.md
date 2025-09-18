# Epic: CIDX Repository Sync Enhancement with CLI Polling Architecture

## Executive Summary

This epic implements complete repository synchronization functionality for CIDX, enabling users to sync git repositories and trigger semantic re-indexing through a synchronous CLI interface that polls asynchronous server operations. The solution maintains familiar CIDX UX patterns while supporting concurrent sync operations with real-time progress reporting.

## Business Value

- **User Efficiency**: One-command repository sync with automatic semantic re-indexing
- **Operational Reliability**: Background job management prevents timeout issues
- **Enhanced UX**: Real-time progress reporting maintains user engagement
- **Scalability**: Concurrent sync support enables multi-project workflows
- **Integration**: Seamless integration with existing CIDX authentication and configuration

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Layer                              │
├─────────────────────────────────────────────────────────────┤
│ • cidx sync command                                         │
│ • Polling loop (1s intervals)                               │
│ • Progress bar rendering                                    │
│ • Error display & recovery                                  │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTPS + JWT
┌──────────────────▼──────────────────────────────────────────┐
│                    API Gateway                              │
├─────────────────────────────────────────────────────────────┤
│ • /sync endpoint (POST)                                     │
│ • /jobs/{id}/status (GET)                                   │
│ • /jobs/{id}/cancel (POST)                                  │
│ • JWT validation                                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                 Job Management Layer                        │
├─────────────────────────────────────────────────────────────┤
│ • SyncJobManager (job lifecycle)                            │
│ • JobPersistence (state storage)                            │
│ • ConcurrencyController (resource limits)                   │
│ • ProgressTracker (real-time updates)                       │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│              Sync Execution Pipeline                        │
├─────────────────────────────────────────────────────────────┤
│ • Phase 1: Git Operations (pull/fetch/merge)                │
│ • Phase 2: Change Detection (diff analysis)                 │
│ • Phase 3: Semantic Indexing (full/incremental)             │
│ • Phase 4: Metadata Updates (stats/timestamps)              │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### CLI Components
- **SyncCommand**: Initiates sync, manages polling loop, displays progress
- **PollingManager**: Handles 1-second interval polling with backoff
- **ProgressRenderer**: Displays real-time progress bars and status
- **ErrorHandler**: Formats and displays user-friendly error messages

### Server Components
- **SyncJobManager**: Creates, tracks, and manages job lifecycle
- **SyncExecutor**: Orchestrates multi-phase sync pipeline
- **GitSyncService**: Handles repository pull operations
- **IndexingService**: Triggers semantic re-indexing
- **JobPersistence**: Stores job state for recovery

### Data Flow
1. CLI sends sync request with JWT token
2. Server creates job, returns job ID
3. Server executes sync phases asynchronously
4. CLI polls job status every second
5. Server returns progress updates
6. CLI renders progress in real-time
7. On completion, CLI displays results

## Implementation Phases

### Phase 1: Foundation (Features 1-2)
- Job infrastructure setup
- Git sync integration
- Basic polling mechanism

### Phase 2: Core Functionality (Features 3-4)
- Semantic indexing pipeline
- Complete CLI implementation
- End-to-end sync workflow

### Phase 3: Polish (Features 5-6)
- Progress reporting system
- Error handling & recovery
- Performance optimization

## Success Metrics

- **Performance**: 95% of syncs complete within 2 minutes
- **Reliability**: 99.9% success rate for standard repositories
- **UX**: Progress updates every 5% completion
- **Scalability**: Support 10 concurrent syncs per user
- **Recovery**: Automatic retry on transient failures

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Large repository timeouts | High | Implement streaming progress, chunked operations |
| Network interruptions | Medium | Automatic retry with exponential backoff |
| Concurrent sync conflicts | Medium | Job queue management, resource locking |
| Index corruption | High | Transactional updates, rollback capability |
| Authentication expiry | Low | Token refresh before long operations |

## Dependencies

- **Existing Systems**:
  - Remote Repository Linking Mode (implemented)
  - JWT authentication system (active)
  - Project-specific configuration (available)
  - Semantic indexing infrastructure (operational)

- **External Services**:
  - Git remote servers (GitHub, GitLab, etc.)
  - Vector database (Qdrant)
  - Embedding service (Ollama/Voyage)

## Epic Completion Checklist

- [ ] **Feature 1: Server-Side Job Infrastructure**
  - [ ] Story 1.1: Job Manager Foundation
  - [ ] Story 1.2: Job Persistence Layer
  - [ ] Story 1.3: Concurrent Job Control

- [ ] **Feature 2: Git Sync Integration**
  - [ ] Story 2.1: Git Pull Operations
  - [ ] Story 2.2: Change Detection System
  - [ ] Story 2.3: Conflict Resolution

- [ ] **Feature 3: Semantic Indexing Pipeline**
  - [ ] Story 3.1: Incremental Indexing
  - [ ] Story 3.2: Full Re-indexing
  - [ ] Story 3.3: Index Validation

- [ ] **Feature 4: CLI Polling Implementation**
  - [ ] Story 4.1: Sync Command Structure
  - [ ] Story 4.2: Polling Loop Engine
  - [ ] Story 4.3: Timeout Management

- [ ] **Feature 5: Progress Reporting System**
  - [ ] Story 5.1: Multi-Phase Progress
  - [ ] Story 5.2: Real-Time Updates
  - [ ] Story 5.3: Progress Persistence

- [ ] **Feature 6: Error Handling & Recovery**
  - [ ] Story 6.1: Error Classification
  - [ ] Story 6.2: Retry Mechanisms
  - [ ] Story 6.3: User Recovery Guidance

## Definition of Done

### Epic Level
- All features implemented and integrated
- End-to-end sync workflow operational
- Performance metrics achieved
- Documentation complete
- Integration tests passing

### Feature Level
- All stories completed
- Feature integration tests passing
- Performance benchmarks met
- Error scenarios handled
- Documentation updated

### Story Level
- Acceptance criteria verified
- Unit tests >90% coverage
- Integration tests passing
- Code review completed
- User-facing functionality available
# Feature: CLI Polling Implementation

## Feature Overview

Implement the synchronous CLI interface that initiates repository sync operations and polls the asynchronous server for job status, providing users with a familiar command-line experience while leveraging background job processing.

## Business Value

- **Familiar UX**: Synchronous CLI interface users expect
- **Responsive Feedback**: Real-time progress without blocking
- **Robust Handling**: Timeouts, retries, and error recovery
- **Clean Integration**: Seamless with existing CIDX commands
- **User Control**: Ability to cancel long-running operations

## Technical Design

### CLI Command Flow

```
┌────────────────┐
│  cidx sync     │
└───────┬────────┘
        ▼
┌────────────────┐
│ Authenticate   │
└───────┬────────┘
        ▼
┌────────────────┐
│ Start Sync Job │
└───────┬────────┘
        ▼
┌────────────────┐
│ Enter Poll Loop│
└───────┬────────┘
        ▼
┌────────────────┐     ┌─────────────┐
│ Check Status   │────►│ Complete?   │
└───────┬────────┘     └──────┬──────┘
        │                     │ No
        │ Yes                 ▼
        ▼              ┌─────────────┐
┌────────────────┐     │   Sleep 1s  │
│ Display Result │     └──────┬──────┘
└────────────────┘            │
                              └──────┘
```

### Component Architecture

```
┌──────────────────────────────────────────┐
│            SyncCommand                   │
├──────────────────────────────────────────┤
│ • parseArguments(args)                   │
│ • authenticate()                         │
│ • initiateSync(options)                  │
│ • pollForCompletion(jobId)              │
│ • displayResults(result)                 │
└─────────────┬────────────────────────────┘
              │
┌─────────────▼────────────────────────────┐
│          PollingManager                  │
├──────────────────────────────────────────┤
│ • pollWithBackoff(jobId, timeout)        │
│ • checkStatus(jobId)                     │
│ • handleProgress(progress)               │
│ • detectStalled(lastUpdate)              │
└─────────────┬────────────────────────────┘
              │
┌─────────────▼────────────────────────────┐
│         TimeoutHandler                   │
├──────────────────────────────────────────┤
│ • enforceTimeout(duration)               │
│ • offerExtension()                       │
│ • cancelOperation(jobId)                 │
│ • cleanupOnExit()                        │
└──────────────────────────────────────────┘
```

## Feature Completion Checklist

- [ ] **Story 4.1: Sync Command Structure**
  - [ ] Command parsing
  - [ ] Authentication flow
  - [ ] Job initiation
  - [ ] Result display

- [ ] **Story 4.2: Polling Loop Engine**
  - [ ] Status checking
  - [ ] Backoff strategy
  - [ ] Progress handling
  - [ ] Completion detection

- [ ] **Story 4.3: Timeout Management**
  - [ ] Timeout enforcement
  - [ ] User interaction
  - [ ] Graceful cancellation
  - [ ] Cleanup procedures

## Dependencies

- HTTP client for API calls
- JWT token management
- Progress bar library
- Signal handling for interrupts

## Success Criteria

- Sync command completes in single invocation
- Progress updates displayed every second
- Timeouts handled gracefully
- User can cancel with Ctrl+C
- Clear error messages on failure

## Risk Considerations

| Risk | Mitigation |
|------|------------|
| Network interruption | Retry with exponential backoff |
| Server unresponsive | Client-side timeout |
| Token expiration | Refresh before long operations |
| Polling overhead | Adaptive polling intervals |
| User abandonment | Clear progress indicators |
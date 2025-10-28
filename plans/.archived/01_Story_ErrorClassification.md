# Story 6.1: Error Classification

## Story Description

As a CIDX error handling system, I need to classify errors by type and severity to determine appropriate recovery strategies and provide users with clear, actionable guidance based on the error category.

## Technical Specification

### Error Taxonomy

```pseudocode
enum ErrorCategory:
    NETWORK          # Connection, timeout, DNS
    AUTHENTICATION   # Token, permissions, expired
    GIT_OPERATION    # Merge, conflict, corruption
    INDEXING         # Embedding, vector DB, parsing
    RESOURCE         # Memory, disk, CPU limits
    CONFIGURATION    # Invalid settings, missing config
    VALIDATION       # Data integrity, format issues
    SYSTEM           # OS, file system, permissions

enum ErrorSeverity:
    WARNING          # Continue with degradation
    RECOVERABLE      # Can retry or workaround
    PERSISTENT       # Needs user intervention
    FATAL            # Must abort operation

class ClassifiedError:
    category: ErrorCategory
    severity: ErrorSeverity
    code: string                    # Unique error code
    message: string                  # User-friendly message
    technicalDetails: string         # For debugging
    context: dict                    # Contextual information
    recoveryStrategy: RecoveryType
    userActions: List<string>        # Suggested actions
    documentationUrl: string         # Help link
```

### Error Classification Rules

```pseudocode
class ErrorClassifier:
    def classify(error: Exception, context: Context) -> ClassifiedError:
        # Network errors
        if isinstance(error, NetworkError):
            if error.isTimeout():
                return ClassifiedError(
                    category=NETWORK,
                    severity=RECOVERABLE,
                    code="NET-001",
                    recoveryStrategy=RETRY_WITH_BACKOFF
                )
            elif error.isDNS():
                return ClassifiedError(
                    category=NETWORK,
                    severity=PERSISTENT,
                    code="NET-002",
                    recoveryStrategy=USER_INTERVENTION
                )

        # Git errors
        elif isinstance(error, GitError):
            if error.isMergeConflict():
                return ClassifiedError(
                    category=GIT_OPERATION,
                    severity=PERSISTENT,
                    code="GIT-001",
                    recoveryStrategy=CONFLICT_RESOLUTION
                )

        # ... more classification rules
```

## Acceptance Criteria

### Error Taxonomy
```gherkin
Given various error types
When defining taxonomy
Then the system should have:
  - 8+ main error categories
  - 4 severity levels
  - Unique error codes
  - Clear categorization rules
  - Comprehensive coverage
And no uncategorized errors
```

### Severity Levels
```gherkin
Given an error occurs
When determining severity
Then the system should classify as:
  - WARNING: Operation continues with issues
  - RECOVERABLE: Can be retried automatically
  - PERSISTENT: Requires user action
  - FATAL: Must abort immediately
And assign appropriate level
```

### Recovery Mapping
```gherkin
Given a classified error
When determining recovery strategy
Then the system should map:
  - Network timeout → Retry with backoff
  - Auth failure → Token refresh
  - Merge conflict → User resolution
  - Resource limit → Scale down operation
  - Fatal error → Clean abort
And provide specific strategy
```

### Context Capture
```gherkin
Given an error occurs
When capturing context
Then the system should record:
  - Timestamp and duration
  - Operation being performed
  - Phase of sync operation
  - File or resource involved
  - System state snapshot
And include in error record
```

### Error Codes
```gherkin
Given error classification
When assigning error codes
Then codes should follow format:
  - Category prefix (NET, AUTH, GIT, etc.)
  - Numeric identifier (001, 002, etc.)
  - Unique across system
  - Documented meanings
  - Searchable in help
And be consistent
```

## Completion Checklist

- [ ] Error taxonomy
  - [ ] Category enumeration
  - [ ] Severity levels
  - [ ] Error code system
  - [ ] Classification rules
- [ ] Severity levels
  - [ ] Level definitions
  - [ ] Escalation rules
  - [ ] User impact assessment
  - [ ] Recovery implications
- [ ] Recovery mapping
  - [ ] Strategy enumeration
  - [ ] Category mapping
  - [ ] Default strategies
  - [ ] Override mechanisms
- [ ] Context capture
  - [ ] Context structure
  - [ ] Capture points
  - [ ] Storage format
  - [ ] Privacy considerations

## Test Scenarios

### Happy Path
1. Network timeout → Classified correctly → Retry strategy
2. Auth expired → Detected properly → Refresh token
3. Disk full → Resource error → Clear message
4. Git conflict → Persistent error → User guidance

### Error Cases
1. Unknown error → Default classification → Generic handling
2. Multiple errors → Prioritized → Most severe first
3. Nested errors → Root cause found → Accurate classification
4. Custom errors → Mapped correctly → Appropriate strategy

### Edge Cases
1. Intermittent errors → Pattern detection → Smart classification
2. Error during recovery → Escalation → Higher severity
3. Timeout during error handling → Bounded → Prevents hang
4. Corrupted error data → Graceful handling → Basic classification

## Performance Requirements

- Classification time: <5ms
- Context capture: <10ms
- Error logging: <20ms
- Memory per error: <1KB
- Error history: 1000 recent errors

## Error Code Reference

### Network Errors (NET-)
| Code | Description | Severity | Recovery |
|------|-------------|----------|----------|
| NET-001 | Connection timeout | Recoverable | Retry with backoff |
| NET-002 | DNS resolution failed | Persistent | Check network settings |
| NET-003 | Connection refused | Persistent | Check server status |
| NET-004 | SSL certificate error | Fatal | Fix certificate |

### Authentication Errors (AUTH-)
| Code | Description | Severity | Recovery |
|------|-------------|----------|----------|
| AUTH-001 | Token expired | Recoverable | Refresh token |
| AUTH-002 | Invalid credentials | Persistent | Re-authenticate |
| AUTH-003 | Insufficient permissions | Fatal | Contact admin |
| AUTH-004 | Account locked | Fatal | Contact support |

### Git Operation Errors (GIT-)
| Code | Description | Severity | Recovery |
|------|-------------|----------|----------|
| GIT-001 | Merge conflict | Persistent | Resolve conflicts |
| GIT-002 | Repository not found | Fatal | Check repository |
| GIT-003 | Corrupted repository | Fatal | Re-clone needed |
| GIT-004 | Branch not found | Persistent | Select valid branch |

### Indexing Errors (IDX-)
| Code | Description | Severity | Recovery |
|------|-------------|----------|----------|
| IDX-001 | Embedding service down | Recoverable | Retry later |
| IDX-002 | Vector DB full | Persistent | Increase storage |
| IDX-003 | File parse error | Warning | Skip file |
| IDX-004 | Corruption detected | Fatal | Full re-index |

## User Message Templates

### Recoverable Error
```
⚠️ Temporary issue detected (NET-001)

Connection to server timed out.
Automatically retrying in 5 seconds...

Retry 1 of 3
```

### Persistent Error
```
❌ Action required (GIT-001)

Merge conflicts detected in 3 files:
  • src/main.py
  • src/config.py
  • tests/test_main.py

Please resolve conflicts manually:
  1. Run 'git status' to see conflicts
  2. Edit files to resolve conflicts
  3. Run 'cidx sync' again

📚 Documentation: https://cidx.io/help/GIT-001
```

### Fatal Error
```
🛑 Fatal error - cannot continue (AUTH-003)

Insufficient permissions to access repository.

This operation requires 'write' access.
Please contact your repository administrator.

Error details saved to: ~/.cidx/errors/AUTH-003-20240115.log
💬 Get support: https://cidx.io/support
```

## Definition of Done

- [ ] Complete error taxonomy defined
- [ ] All severity levels implemented
- [ ] Error classification rules complete
- [ ] Recovery strategies mapped
- [ ] Context capture working
- [ ] Error codes documented
- [ ] User messages templated
- [ ] Unit tests >90% coverage
- [ ] Integration tests cover all categories
- [ ] Performance requirements met
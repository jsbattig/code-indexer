# Story 2.2: Change Detection and Auto-Indexing

## Story Description

As a developer using CIDX sync, I want the system to automatically trigger re-indexing when changes are detected after git pull operations, so that query results remain accurate and up-to-date with the codebase.

## Business Context

The core value of CIDX is providing accurate query results. If code changes after a git pull but the index isn't updated, queries return stale/incorrect results, making the system worthless. Simple solution: detect any changes → trigger re-index.

## Technical Specification

### Simple Change Detection Logic

```pseudocode
after git_pull:
    if before_commit != after_commit:
        run_command("cidx index")
        log("Re-indexing triggered due to code changes")
    else:
        log("No changes detected, index remains current")
```

### Implementation Requirements

- Check commit hash before and after git pull
- If different → run `cidx index` command in repository directory
- Log success/failure of indexing operation
- Allow configuration to enable/disable auto-indexing
- Non-blocking: sync succeeds even if indexing fails
- Reasonable timeout (5 minutes) to prevent hanging

## User Story

**As a** developer using CIDX sync
**I want** automatic re-indexing when code changes are pulled
**So that** my queries always return accurate, up-to-date results

## Acceptance Criteria

### Core Functionality
- [ ] ✅ System detects if ANY changes occurred during git pull (before_commit != after_commit)
- [ ] ✅ When changes are detected, system automatically triggers 'cidx index' command
- [ ] ✅ System reports whether indexing was triggered in sync results
- [ ] ✅ Auto-indexing can be enabled/disabled via configuration
- [ ] ✅ System logs indexing success/failure for troubleshooting
- [ ] ✅ Indexing operation has reasonable timeout (5 minutes) to prevent hanging
- [ ] ✅ System continues to function if indexing fails (non-blocking)

### Implementation Details

```python
# In GitSyncExecutor
def execute_pull(self):
    before_commit = get_current_commit()
    # ... perform git pull ...
    after_commit = get_current_commit()

    changes_detected = before_commit != after_commit
    indexing_triggered = False

    if changes_detected and self.auto_index_on_changes:
        indexing_triggered = self._trigger_cidx_index()

    return GitSyncResult(
        success=True,
        changes_detected=changes_detected,
        indexing_triggered=indexing_triggered,
        ...
    )
```

## Definition of Done

- [ ] ✅ Git pull detects any changes via commit hash comparison
- [ ] ✅ Changes trigger automatic `cidx index` execution
- [ ] ✅ Configuration option to enable/disable auto-indexing
- [ ] ✅ Proper logging and error handling
- [ ] ✅ Results include indexing status information
- [ ] ✅ System remains functional if indexing fails
- [ ] ✅ Implementation tested with real git repositories

## Priority: HIGH

This is essential functionality. Without it, the sync feature provides no value because queries become inaccurate after code changes.
# Storage Command Routing Update Summary

## Overview

Updated the CIDX Daemonization epic to add storage management command routing for cache coherence. This ensures that commands that modify disk storage (`clean`, `clean-data`, `status`) are routed through the daemon to maintain cache coherence.

## Problem Statement

**Cache Coherence Issue:** Storage management commands were modifying disk storage while the daemon had cached indexes in memory, causing the daemon cache to point to deleted/modified data.

**Example:**
- Daemon has indexes cached in memory
- User runs `cidx clean-data` (runs locally, deletes disk storage)
- Daemon cache now points to deleted data
- Next query fails or returns stale results

## Solution

Route storage commands through the daemon so it can invalidate its cache BEFORE performing storage operations.

## Changes Made

### 1. Epic Overview (Feat_CIDXDaemonization.md)

**Updated:**
- Command routing matrix: 12 → 13 routed commands
- Added comprehensive command routing breakdown (29 total commands)
- Added "Cache Coherence for Storage Operations" section explaining the problem and solution
- Updated RPyC Service Interface to include 3 new storage methods
- Updated Business Value to include cache coherence
- Updated Total Effort: 11 → 12 days

**New Methods Added:**
- `exposed_clean()` - Clear vectors + invalidate cache
- `exposed_clean_data()` - Clear project data + invalidate cache
- `exposed_status()` - Get combined daemon + storage status

### 2. Story 2.1: RPyC Daemon Service (02_Story_RPyCDaemonService.md)

**Updated:**
- Story Points: 10 → 11 (4 → 4.5 days)
- Story overview to include cache-coherent storage operations
- Added 3 new exposed methods with full implementations
- Added 5 new acceptance criteria for storage operations
- Added 3 new test cases for cache invalidation

**Implementation Details:**
- All storage methods acquire write lock for serialization
- Cache invalidation happens BEFORE storage operations
- Methods return status with `cache_invalidated` flag

### 3. Story 2.3: Client Delegation (04_Story_ClientDelegation.md)

**Updated:**
- Story Points: 6 → 7 (2.5 → 3 days)
- Story overview to include storage operations
- Added 3 new command implementations (clean, clean-data, status)
- Added 3 delegation functions for daemon routing
- Added 5 new acceptance criteria for storage routing
- Added 3 new test cases for command routing

**Routing Logic:**
- Commands check `daemon.enabled` config
- Route to daemon when enabled, fallback to standalone when disabled
- Status command shows daemon info when routed to daemon

## Command Routing Summary

### Total Commands: 29

**Routed to Daemon (13):**
- Query operations: `query`, `query --fts`, `query --fts --semantic`
- Indexing: `index`, `watch`, `watch-stop`
- **Storage (NEW):** `clean`, `clean-data`, `status`
- Daemon control: `daemon status`, `daemon clear-cache`, `start`, `stop`

**Always Local (16):**
- Configuration: `init`, `fix-config`
- Container management: `force-flush`, `optimize`, `list-collections`, etc.
- Remote mode: `admin`, `auth`, `jobs`, `repos`, `sync`, `system`
- Utility: `teach-ai`

## Cache Coherence Flow

### Before (Problem):
```
Daemon cached → User runs clean → Disk cleared → Cache stale → Query fails
```

### After (Solution):
```
Daemon cached → clean routes to daemon → Cache invalidated → Disk cleared → Cache coherent
```

## Impact

### Epic Total:
- Previous: 11 days
- Updated: 12 days (+1 day for storage operations)

### Story Points:
- Story 2.1: 10 → 11 points (+0.5 days)
- Story 2.3: 6 → 7 points (+0.5 days)

## Implementation Pattern

All storage operations follow the same pattern:

1. Acquire write lock (serialize with other operations)
2. Invalidate cache FIRST (clear cached indexes)
3. Execute storage operation SECOND
4. Return status with `cache_invalidated: true`

## Testing Coverage

**Added Unit Tests:**
- `test_clean_invalidates_cache()` - Verify cache cleared
- `test_clean_data_invalidates_cache()` - Verify cache cleared
- `test_status_includes_daemon_info()` - Verify combined status

**Added Integration Tests:**
- `test_clean_routes_to_daemon()` - Verify command routing
- `test_clean_data_routes_to_daemon()` - Verify command routing
- `test_status_shows_daemon_info()` - Verify daemon info display

## Backward Compatibility

- No breaking changes to command interface
- Commands work identically in standalone mode
- Only routing changes when daemon enabled
- Graceful fallback if daemon unavailable

## Success Metrics

- Cache coherence maintained after all storage operations
- No stale cache references after clean operations
- Status command shows daemon cache state when enabled
- All tests passing with cache invalidation verified

## Files Modified

1. `/plans/active/02_Feat_CIDXDaemonization/Feat_CIDXDaemonization.md`
2. `/plans/active/02_Feat_CIDXDaemonization/02_Story_RPyCDaemonService.md`
3. `/plans/active/02_Feat_CIDXDaemonization/04_Story_ClientDelegation.md`

## Next Steps

Implementation can proceed with these specifications. The cache coherence issue is fully addressed through proper command routing and cache invalidation patterns.
# Story 11.1: Single Project Data Cleanup

## 🎯 **Story Intent**

Validate single project data cleanup functionality to ensure users can quickly reset project state without stopping containers for fast development cycles.

[Manual Testing Reference: "Single project cleanup validation"]

## 📋 **Story Description**

**As a** Developer using CIDX
**I want to** clean my current project's data without stopping containers
**So that** I can quickly reset project state between tests and development sessions

[Conversation Reference: "Fast project data cleanup while preserving container performance"]

## 🔧 **Test Procedures**

### Test 11.1.1: Basic Project Data Cleanup
**Command to Execute:**
```bash
cd /path/to/project
python -m code_indexer.cli clean-data
```

**Expected Results:**
- Clears Qdrant collections for current project
- Removes local cache directories
- Preserves running containers and their state
- Returns cleanup success confirmation
- Maintains container networks and volumes

**Pass/Fail Criteria:**
- ✅ PASS: Data cleanup successful with containers preserved
- ❌ FAIL: Cleanup fails or containers inappropriately affected

### Test 11.1.2: Cleanup with Verification
**Command to Execute:**
```bash
cd /path/to/project
python -m code_indexer.cli clean-data --verify
```

**Expected Results:**
- Performs cleanup operations
- Validates that cleanup operations succeeded
- Reports verification results
- Confirms containers remain running and healthy
- Provides detailed cleanup status

**Pass/Fail Criteria:**
- ✅ PASS: Cleanup verified successful with detailed status
- ❌ FAIL: Verification fails or reports cleanup issues

### Test 11.1.3: Container State Verification Post-Cleanup
**Command to Execute:**
```bash
cd /path/to/project
python -m code_indexer.cli status
```

**Expected Results:**
- Containers show as running and healthy
- Services respond correctly to health checks
- Qdrant collections show as empty/reset
- System ready for fresh indexing operations
- No container restart required

**Pass/Fail Criteria:**
- ✅ PASS: Containers healthy with clean data state
- ❌ FAIL: Container issues or unhealthy post-cleanup state

### Test 11.1.4: Fast Re-initialization After Cleanup
**Command to Execute:**
```bash
cd /path/to/project
python -m code_indexer.cli start
```

**Expected Results:**
- Start command completes much faster than full initialization
- Services connect immediately without container startup delays
- System ready for indexing operations
- Performance benefits of container preservation evident

**Pass/Fail Criteria:**
- ✅ PASS: Fast startup demonstrating container preservation benefits
- ❌ FAIL: Slow startup indicating containers were unnecessarily stopped

## 📊 **Success Metrics**

- **Cleanup Speed**: Significantly faster than full `uninstall` operation
- **Container Preservation**: 100% container uptime through cleanup process
- **Data Reset**: Complete clearing of project-specific data
- **Restart Performance**: <50% time of full initialization for subsequent starts

## 🎯 **Acceptance Criteria**

- [ ] Project data cleanup completes successfully
- [ ] Containers remain running throughout cleanup process
- [ ] Qdrant collections properly reset to empty state
- [ ] Local cache directories cleared appropriately
- [ ] Verification option provides accurate cleanup status
- [ ] Subsequent operations benefit from preserved container state

## 📝 **Manual Testing Notes**

**Prerequisites:**
- CIDX project with indexed data and running containers
- Sufficient disk space for cleanup operations
- No critical data that cannot be regenerated
- Understanding that cleanup removes indexed data

**Test Environment Setup:**
1. Index some content to create data for cleanup
2. Verify containers are running and healthy
3. Note current container states and resource usage
4. Prepare to measure cleanup and restart performance

**Cleanup Testing Scenarios:**
- Project with substantial indexed data
- Project with multiple Qdrant collections
- Project with cached embedding data
- Empty project (edge case testing)

**Post-Test Validation:**
1. Verify all project data successfully cleared
2. Confirm containers maintained running state
3. Test fresh indexing operations work correctly
4. Measure performance improvement over full restart

**Common Issues:**
- Permission issues with cache directory cleanup
- Container health check failures during cleanup
- Incomplete Qdrant collection clearing
- Network connectivity issues affecting verification

**Performance Comparison:**
- Measure cleanup time vs `uninstall` + `init` + `start` sequence
- Compare restart times after cleanup vs full reinstallation
- Document container resource usage preservation

[Manual Testing Reference: "Single project cleanup validation procedures"]
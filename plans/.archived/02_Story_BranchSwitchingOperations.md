# Story 9.2: Branch Switching Operations

## 🎯 **Story Intent**

Validate repository branch switching functionality through remote API to ensure users can change branches for different development contexts.

[Manual Testing Reference: "Branch switching API validation"]

## 📋 **Story Description**

**As a** Developer using remote CIDX
**I want to** switch between available branches in my activated repositories
**So that** I can work on different features or examine different code states

[Conversation Reference: "Branch switching and git operations"]

## 🔧 **Test Procedures**

### Test 9.2.1: Switch to Existing Local Branch
**Command to Execute:**
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"branch_name": "develop"}' \
     "http://127.0.0.1:8095/api/repos/code-indexer/switch-branch"
```

**Expected Results:**
- Successfully switches to specified local branch
- Returns confirmation message with branch name
- Updates repository metadata with new current branch
- Maintains repository state consistency

**Pass/Fail Criteria:**
- ✅ PASS: Branch switch successful with proper confirmation
- ❌ FAIL: Switch fails or repository left in inconsistent state

### Test 9.2.2: Checkout Remote Branch as Local
**Command to Execute:**
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"branch_name": "feature/new-feature"}' \
     "http://127.0.0.1:8095/api/repos/code-indexer/switch-branch"
```

**Expected Results:**
- Creates local tracking branch from remote
- Performs git fetch operation if needed
- Sets up proper remote tracking relationship
- Confirms successful checkout operation

**Pass/Fail Criteria:**
- ✅ PASS: Remote branch checked out with tracking setup
- ❌ FAIL: Checkout fails or tracking not properly configured

### Test 9.2.3: Switch Back to Main Branch
**Command to Execute:**
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"branch_name": "master"}' \
     "http://127.0.0.1:8095/api/repos/code-indexer/switch-branch"
```

**Expected Results:**
- Returns to main/master branch successfully
- Repository working directory reflects branch content
- Metadata updated to show current branch
- No uncommitted changes lost (if any existed)

**Pass/Fail Criteria:**
- ✅ PASS: Main branch switch successful with clean state
- ❌ FAIL: Switch fails or working directory corrupted

### Test 9.2.4: Verify Branch Switch in Subsequent Listing
**Command to Execute:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8095/api/repos/code-indexer/branches" | jq '.current_branch'
```

**Expected Results:**
- Current branch reflects the last successful switch
- Branch listing shows updated current branch indicator
- Repository metadata consistency maintained
- Git working directory matches API state

**Pass/Fail Criteria:**
- ✅ PASS: Branch state consistency across all interfaces
- ❌ FAIL: Inconsistent branch state between API and git

## 📊 **Success Metrics**

- **Switch Response Time**: <5 seconds for local branches, <10 seconds for remote
- **State Consistency**: 100% accuracy between API and actual git state
- **Error Recovery**: Clean failure handling without repository corruption
- **Remote Fetch Success**: Successful checkout of remote branches when accessible

## 🎯 **Acceptance Criteria**

- [ ] Local branch switching completes successfully
- [ ] Remote branch checkout creates proper local tracking branches
- [ ] Branch switches update repository metadata correctly
- [ ] Current branch information accurate after all switch operations
- [ ] Git working directory reflects the active branch content
- [ ] No data loss or repository corruption during branch operations

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Repository with multiple existing branches (local and remote)
- Valid authentication and activated repository
- Clean working directory (no uncommitted changes)
- Network access for remote branch operations

**Test Environment Setup:**
1. Create test branches if needed for comprehensive testing
2. Ensure clean working directory before branch switching
3. Verify remote repository access for remote branch testing
4. Backup repository state for recovery if needed

**Branch Switching Scenarios:**
- Switch between existing local branches
- Checkout remote branches that don't exist locally
- Return to main branch from feature branches
- Handle branches with different content/file structures

**Post-Test Validation:**
1. Verify git status matches API responses
2. Confirm working directory reflects branch content
3. Check that subsequent operations work correctly
4. Validate repository metadata accuracy

**Common Issues:**
- Uncommitted changes preventing branch switches
- Network issues affecting remote branch access
- Permission problems with git operations
- Repository state corruption requiring cleanup

**Error Testing:**
- Attempt switch to non-existent branch
- Test behavior with uncommitted local changes
- Verify error messages are clear and actionable

[Manual Testing Reference: "Branch switching API validation procedures"]
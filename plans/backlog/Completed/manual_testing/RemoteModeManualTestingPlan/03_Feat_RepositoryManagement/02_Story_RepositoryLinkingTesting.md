# Story 3.2: Intelligent Branch Matching Testing

## 🎯 **Story Intent**

Validate intelligent branch matching and git-aware repository linking through systematic manual testing procedures.

[Conversation Reference: "Repository linking validation"]

## 📋 **Story Description**

**As a** Developer
**I want to** have my queries automatically matched to the correct branch on the remote repository
**So that** I can query against remote indexes that match my current git working context

[Conversation Reference: "Each test story specifies exact python -m code_indexer.cli commands to execute"]

## 🔧 **Test Procedures**

### Test 3.2.1: Exact Branch Name Matching
**Command to Execute:**
```bash
# Switch to a specific branch locally
git checkout main
python -m code_indexer.cli query "branch matching test on main" --limit 5
```

**Expected Results:**
- Query automatically matches to 'main' branch on remote repository
- Repository linking uses exact branch name when available
- Query results come from main branch of remote repository
- Branch context visible in query results or status

**Pass/Fail Criteria:**
- ✅ PASS: Query executes against correct remote branch (main)
- ❌ FAIL: Incorrect branch context or branch matching failure

[Conversation Reference: "Clear pass/fail criteria for manual verification"]

### Test 3.2.2: Branch Fallback Hierarchy Testing
**Command to Execute:**
```bash
# Switch to a local-only branch
git checkout -b feature-test-branch
python -m code_indexer.cli query "branch fallback test" --limit 5
```

**Expected Results:**
- System detects local branch doesn't exist on remote
- Automatic fallback to git merge-base analysis
- Links to appropriate remote branch based on git topology
- Clear indication of which remote branch was selected

**Pass/Fail Criteria:**
- ✅ PASS: Intelligent branch fallback selects appropriate remote branch
- ❌ FAIL: Branch fallback fails or selects inappropriate branch
### Test 3.2.3: Branch Context Switching
**Command to Execute:**
```bash
# Switch to develop branch and query
git checkout develop
python -m code_indexer.cli query "develop branch context test" --limit 3
```

**Expected Results:**
- Query automatically adjusts to develop branch context
- Remote query targets develop branch on remote repository
- Branch context switching handled seamlessly
- No manual repository relinking required

**Pass/Fail Criteria:**
- ✅ PASS: Branch context switching works automatically
- ❌ FAIL: Branch context not updated or incorrect remote branch

### Test 3.2.4: Git Merge-Base Analysis
**Command to Execute:**
```bash
# Create local branch and make commits
git checkout -b feature-advanced-search
# Make some commits, then query
python -m code_indexer.cli query "merge base analysis test" --limit 3
```

**Expected Results:**
- System analyzes git topology using merge-base
- Selects appropriate remote branch based on git history
- Clear indication of which remote branch was matched
- Query results appropriate for branch context

**Pass/Fail Criteria:**
- ✅ PASS: Git merge-base analysis selects appropriate remote branch
- ❌ FAIL: Poor branch selection or merge-base analysis failure

### Test 3.2.5: Repository Link Persistence
**Command to Execute:**
```bash
# Exit and restart CIDX to test persistence
python -m code_indexer.cli status
```

**Expected Results:**
- Repository linking information persists across sessions
- No re-linking required after restart
- Branch context maintained correctly
- Status shows established repository connection

**Pass/Fail Criteria:**
- ✅ PASS: Repository links persist correctly across sessions
- ❌ FAIL: Repository linking lost or corrupted after restart

### Test 3.2.6: Multiple Remote Repository Handling
**Command to Execute:**
```bash
# Test with git repository that has multiple remotes
git remote add upstream https://github.com/upstream/repo.git
python -m code_indexer.cli query "multiple remotes test" --limit 3
```

**Expected Results:**
- System handles multiple git remotes appropriately
- Selects correct remote for repository matching
- Clear indication of which remote was used
- No confusion between different remote URLs

**Pass/Fail Criteria:**
- ✅ PASS: Multiple remotes handled correctly with appropriate selection
- ❌ FAIL: Remote selection confusion or incorrect repository matching

## 📊 **Success Metrics**

- **Branch Matching Accuracy**: >95% correct branch selection
- **Merge-Base Analysis**: Intelligent topology-based branch selection
- **Link Persistence**: Repository links maintained across sessions
- **Remote Handling**: Multiple git remotes handled appropriately

[Conversation Reference: "Intelligent branch matching testing using git merge-base analysis"]

## 🎯 **Acceptance Criteria**

- [ ] Exact branch name matching works when remote branch exists
- [ ] Branch fallback hierarchy selects appropriate alternatives
- [ ] Git merge-base analysis provides intelligent branch matching
- [ ] Branch context switching works automatically during queries
- [ ] Repository linking persists correctly across CIDX sessions
- [ ] Multiple git remotes handled with appropriate remote selection
- [ ] All branch matching provides clear feedback about selections

[Conversation Reference: "Clear acceptance criteria for manual assessment"]

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Local git repository with multiple branches (main, develop, feature branches)
- Remote server with corresponding repository and branches indexed
- Git repository with proper remote configuration
- CIDX remote mode initialized and authenticated

**Test Environment Setup:**
1. Prepare git repository with diverse branch structure
2. Ensure remote repository has corresponding branches indexed
3. Test both exact matches and fallback scenarios
4. Verify git remotes are properly configured

**Post-Test Validation:**
1. Confirm branch matching logic produces expected results
2. Verify git merge-base analysis works correctly
3. Test that branch context changes are reflected in queries
4. Validate repository linking survives session restarts

[Conversation Reference: "Manual execution environment with python -m code_indexer.cli CLI"]
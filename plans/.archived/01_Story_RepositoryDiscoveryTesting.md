# Story 3.1: Automatic Repository Linking Testing

## 🎯 **Story Intent**

Validate automatic repository linking during first query execution, ensuring seamless connection between local git repositories and remote indexed repositories.

[Conversation Reference: "Repository discovery testing"]

## 📋 **Story Description**

**As a** Developer
**I want to** have my local git repository automatically linked to the corresponding remote repository
**So that** I can query remote indexes without manual repository selection or linking commands

[Conversation Reference: "Each test story specifies exact python -m code_indexer.cli commands to execute"]

## 🔧 **Test Procedures**

### Test 3.1.1: First Query with Automatic Repository Linking
**Command to Execute:**
```bash
python -m code_indexer.cli query "test query for repository linking" --limit 5
```

**Expected Results:**
- Query triggers automatic repository linking on first execution
- Local git origin URL matched to remote repository automatically
- Repository linking success message displayed
- Query executes successfully against linked remote repository
- Repository link information stored for subsequent queries

**Pass/Fail Criteria:**
- ✅ PASS: Automatic repository linking succeeds with successful query execution
- ❌ FAIL: Repository linking fails or query cannot access remote repository

[Conversation Reference: "Clear pass/fail criteria for manual verification"]

### Test 3.1.2: Repository Linking Status Verification
**Command to Execute:**
```bash
python -m code_indexer.cli status
```

**Expected Results:**
- Status shows successful repository linking information
- Displays linked repository alias or identifier
- Shows branch context and remote server connection
- Confirms repository is available for querying

**Pass/Fail Criteria:**
- ✅ PASS: Status clearly shows repository linking and remote connection details
- ❌ FAIL: Missing repository linking information or unclear status
### Test 3.1.3: Subsequent Query with Established Link
**Command to Execute:**
```bash
python -m code_indexer.cli query "second query to verify repository link persistence" --limit 3
```

**Expected Results:**
- Query executes immediately without repository linking process
- Uses established repository link from previous query
- No additional linking messages or delays
- Query results returned from correct remote repository

**Pass/Fail Criteria:**
- ✅ PASS: Query executes seamlessly using existing repository link
- ❌ FAIL: Repository linking process repeats unnecessarily

### Test 3.1.4: Repository Linking Error Handling
**Command to Execute:**
```bash
# Test from directory with no git origin or non-matching repository
python -m code_indexer.cli query "test query for linking error" --limit 5
```

**Expected Results:**
- Clear error message about repository linking failure
- Helpful guidance about git origin URL requirements
- Suggestion to check remote repository availability
- No partial or corrupted repository links created

**Pass/Fail Criteria:**
- ✅ PASS: Repository linking errors handled gracefully with clear guidance
- ❌ FAIL: Cryptic errors or failed repository linking attempts

## 📊 **Success Metrics**

- **Linking Speed**: Automatic repository linking completes within 10 seconds
- **Link Accuracy**: Local git origin correctly matched to remote repository
- **Link Persistence**: Repository links persist across query sessions
- **Error Clarity**: Repository linking failures provide actionable guidance

[Conversation Reference: "Performance Requirements: Query responses within 2 seconds for typical operations"]

## 🎯 **Acceptance Criteria**

- [ ] First query automatically links local git repository to remote repository
- [ ] Repository linking status visible in python -m code_indexer.cli status command
- [ ] Subsequent queries use established repository link without relinking
- [ ] Repository linking failures handled with clear error messages
- [ ] Automatic linking works with git topology analysis
- [ ] Repository link information persists between sessions

[Conversation Reference: "Clear acceptance criteria for manual assessment"]

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Local directory is a git repository with remote origin URL
- CIDX remote mode initialized and authenticated
- Remote server has corresponding repository indexed
- Network connectivity to remote server

**Test Environment Setup:**
1. Ensure local directory has proper git configuration with origin URL
2. Verify remote server has matching repository indexed
3. Start with clean state (no existing repository links)
4. Prepare test scenarios with and without matching repositories

**Post-Test Validation:**
1. Verify repository link information stored in .code-indexer directory
2. Confirm git origin URL matching works correctly
3. Test repository link persistence across CIDX sessions
4. Validate automatic linking handles edge cases gracefully

[Conversation Reference: "Manual execution environment with python -m code_indexer.cli CLI"]
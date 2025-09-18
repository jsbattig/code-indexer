# Story 9.1: Branch Listing Operations

## 🎯 **Story Intent**

Validate repository branch listing functionality through remote API to ensure users can discover available branches for development work.

[Manual Testing Reference: "Branch listing API validation"]

## 📋 **Story Description**

**As a** Developer using remote CIDX
**I want to** list all available branches in my activated repositories
**So that** I can see what branches exist for switching and development

[Conversation Reference: "Branch discovery and information display"]

## 🔧 **Test Procedures**

### Test 9.1.1: Basic Branch Listing via API
**Command to Execute:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8095/api/repos/code-indexer/branches"
```

**Expected Results:**
- Returns JSON with branch information
- Includes both local and remote branches
- Shows current branch indicator
- Displays total branch counts

**Pass/Fail Criteria:**
- ✅ PASS: API returns complete branch listing with accurate information
- ❌ FAIL: API fails or returns incomplete/incorrect branch data

### Test 9.1.2: Branch Information Details
**Command to Execute:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8095/api/repos/code-indexer/branches" | jq '.'
```

**Expected Results:**
- Each branch shows commit hash, message, and date
- Branch types properly identified (local/remote)
- Current branch clearly marked
- Remote references properly formatted

**Pass/Fail Criteria:**
- ✅ PASS: All branch details accurate and properly formatted
- ❌ FAIL: Missing or incorrect branch information

### Test 9.1.3: Golden Repository Branch Listing
**Command to Execute:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8095/api/repos/golden/code-indexer/branches"
```

**Expected Results:**
- Lists branches available in golden repository
- Shows default branch indication
- Provides branch creation timestamps
- Includes remote branch availability

**Pass/Fail Criteria:**
- ✅ PASS: Golden repository branches listed accurately
- ❌ FAIL: Missing branches or incorrect golden repo information

### Test 9.1.4: Error Handling for Invalid Repository
**Command to Execute:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8095/api/repos/nonexistent/branches"
```

**Expected Results:**
- Returns appropriate HTTP error code (404)
- Provides clear error message
- Maintains API error response format
- No system crashes or unexpected behavior

**Pass/Fail Criteria:**
- ✅ PASS: Proper error handling with clear messages
- ❌ FAIL: System crashes or unclear error responses

## 📊 **Success Metrics**

- **API Response Time**: <2 seconds for branch listing
- **Data Accuracy**: 100% match with actual git branch information
- **Error Handling**: Clear, actionable error messages for all failure cases
- **Information Completeness**: All relevant branch metadata included

## 🎯 **Acceptance Criteria**

- [ ] Branch listing API returns complete and accurate branch information
- [ ] Local and remote branches properly distinguished and labeled
- [ ] Current branch clearly identified in API responses
- [ ] Branch commit information (hash, message, date) displayed correctly
- [ ] Golden repository branch listing works independently
- [ ] Error handling provides clear feedback for invalid requests

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Active remote CIDX server on localhost:8095
- Valid JWT authentication token
- Activated repository with multiple branches available
- Golden repository configured with branch history

**Test Environment Setup:**
1. Ensure repository has multiple local and remote branches
2. Verify authentication token is valid and not expired
3. Confirm repository activation completed successfully
4. Prepare invalid repository names for error testing

**Branch Testing Scenarios:**
- Repository with only main/master branch
- Repository with multiple feature branches
- Repository with remote branches not yet checked out locally
- Repository with conflicted or problematic git state

**Post-Test Validation:**
1. Compare API results with direct git command output
2. Verify all branch types properly represented
3. Confirm branch switching preparation data accuracy
4. Validate error responses meet API standards

**Common Issues:**
- Token expiration during testing
- Git repository state affecting branch listing
- Network connectivity issues with remote branches
- Permissions problems with repository access

[Manual Testing Reference: "Branch listing API validation procedures"]
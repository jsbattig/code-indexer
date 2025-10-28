# Story 10.1: Basic Credential Update Operations

## 🎯 **Story Intent**

Validate the credential rotation functionality to ensure users can securely update their authentication credentials while preserving all project configuration.

[Manual Testing Reference: "Credential update validation"]

## 📋 **Story Description**

**As a** Developer using remote CIDX
**I want to** update my authentication credentials (username/password)
**So that** I can maintain access when my credentials change without losing project setup

[Conversation Reference: "Secure credential rotation with configuration preservation"]

## 🔧 **Test Procedures**

### Test 10.1.1: Current Credential Validation
**Command to Execute:**
```bash
cd /path/to/remote/project
python -m code_indexer.cli status
```

**Expected Results:**
- Status shows successful server connection
- Authentication working with current credentials
- Repository links active and accessible
- No credential or connection errors

**Pass/Fail Criteria:**
- ✅ PASS: Current authentication working properly
- ❌ FAIL: Existing credentials already failing

### Test 10.1.2: Credential Update with Valid Credentials
**Command to Execute:**
```bash
cd /path/to/remote/project
python -m code_indexer.cli auth update --username admin --password admin123
```

**Expected Results:**
- Command validates new credentials against server
- Backup created before credential changes
- New credentials stored securely and encrypted
- Success message confirming credential update
- Repository configuration preserved

**Pass/Fail Criteria:**
- ✅ PASS: Credential update successful with validation
- ❌ FAIL: Update fails or configuration corrupted

**Known Issue**: Current implementation has validation bug - may reject working credentials

### Test 10.1.3: Post-Update Authentication Verification
**Command to Execute:**
```bash
cd /path/to/remote/project
python -m code_indexer.cli status
```

**Expected Results:**
- Status shows continued server connectivity
- Authentication works with new credentials
- Repository links remain intact
- No service disruption from credential change

**Pass/Fail Criteria:**
- ✅ PASS: Authentication working with updated credentials
- ❌ FAIL: Authentication fails or configuration lost

### Test 10.1.4: Token Invalidation Verification
**Command to Execute:**
```bash
cd /path/to/remote/project
python -m code_indexer.cli query "test query" --quiet
```

**Expected Results:**
- Query executes successfully with new authentication
- Old cached tokens properly invalidated
- Fresh authentication tokens obtained
- No authentication conflicts or cached token issues

**Pass/Fail Criteria:**
- ✅ PASS: Fresh authentication tokens working properly
- ❌ FAIL: Cached token issues or authentication failures

## 📊 **Success Metrics**

- **Security Validation**: Credentials tested against server before storage
- **Configuration Preservation**: 100% retention of repository links and settings
- **Token Management**: Complete invalidation of old cached tokens
- **Encryption Security**: New credentials properly encrypted in storage

## 🎯 **Acceptance Criteria**

- [ ] Current working credentials properly identified before update
- [ ] New credentials validated against server before storage
- [ ] Credential update process preserves all repository configuration
- [ ] Post-update authentication works with new credentials
- [ ] Cached tokens properly invalidated and refreshed
- [ ] Error handling provides clear feedback for validation failures

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Working remote CIDX project with valid current credentials
- Access to valid alternative credentials for testing
- Network connectivity to CIDX server for validation
- Backup project directory recommended for safety

**Test Environment Setup:**
1. Verify current authentication is working properly
2. Identify valid alternative credentials for testing
3. Backup project directory as safety measure
4. Ensure network access to server for validation

**Credential Update Scenarios:**
- Same username, different password
- Different username, same password
- Both username and password changed
- Update with currently working credentials (should succeed)

**Post-Test Validation:**
1. Verify authentication works with new credentials
2. Confirm all repository links remain functional
3. Test semantic queries work with new authentication
4. Validate backup files created during process

**Common Issues:**
- **Known Bug**: Validation may reject working credentials
- Network connectivity affecting server validation
- Permission issues with credential file updates
- Token caching causing authentication conflicts

**Error Recovery:**
- Check for backup files if credential update fails
- Manually restore from `.remote-config.backup` if needed
- Re-run original authentication setup if corruption occurs

[Manual Testing Reference: "Credential rotation validation procedures"]
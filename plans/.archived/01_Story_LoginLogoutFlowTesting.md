# Story 2.1: Automatic Authentication Testing

## 🎯 **Story Intent**

Validate automatic authentication flows including credential storage, JWT token management, and transparent authentication during query operations.

[Conversation Reference: "Authentication flows, token lifecycle management"]

## 📋 **Story Description**

**As a** Developer
**I want to** authenticate automatically with the remote CIDX server using stored credentials
**So that** I can query remote repositories seamlessly without explicit login commands

[Conversation Reference: "Test authentication flows and security features"]

## 🔧 **Test Procedures**

### Test 2.1.1: Remote Initialization with Authentication
**Command to Execute:**
```bash
python -m code_indexer.cli init --remote https://server.example.com --username testuser --password testpass
```

**Expected Results:**
- Remote mode initialization succeeds with valid credentials
- Encrypted credentials stored in .code-indexer/.creds
- Server connectivity and authentication validated
- Success message confirms remote mode setup

**Pass/Fail Criteria:**
- ✅ PASS: Successful initialization with secure credential storage
- ❌ FAIL: Initialization fails or insecure credential handling

[Conversation Reference: "JWT tokens are acquired and stored securely"]

### Test 2.1.2: Invalid Credentials During Initialization
**Command to Execute:**
```bash
python -m code_indexer.cli init --remote https://server.example.com --username invalid --password wrongpass
```

**Expected Results:**
- Remote initialization fails with clear error message
- No credentials stored or cached
- Error message suggests credential verification
- Appropriate exit code returned

**Pass/Fail Criteria:**
- ✅ PASS: Clear error message, no credential storage
- ❌ FAIL: Unclear error or partial initialization state

### Test 2.1.3: Automatic Authentication During Query
**Command to Execute:**
```bash
python -m code_indexer.cli query "authentication test" --limit 5
```

**Expected Results:**
- Query executes automatically using stored credentials
- JWT token acquired transparently during query execution
- No explicit authentication commands required
- Query results returned normally

**Pass/Fail Criteria:**
- ✅ PASS: Seamless automatic authentication with query execution
- ❌ FAIL: Authentication errors or manual intervention required

### Test 2.1.4: Token Refresh Mechanism
**Command to Execute:**
```bash
# Wait for token to near expiration, then query
python -m code_indexer.cli query "token refresh test" --limit 3
```

**Expected Results:**
- Token refresh triggered automatically before expiration
- New token acquired without user intervention
- Query executes successfully with refreshed token
- No visible authentication prompts to user

**Pass/Fail Criteria:**
- ✅ PASS: Automatic token refresh without user intervention
- ❌ FAIL: Token expiration causes query failure

## 📊 **Success Metrics**

- **Initialization Speed**: Remote initialization completes in <10 seconds
- **Token Security**: No plaintext token storage or logging
- **Session Persistence**: Automatic authentication across query sessions
- **Token Management**: Transparent token refresh without user intervention

[Conversation Reference: "Authentication Speed: Token acquisition completes in <5 seconds"]

## 🎯 **Acceptance Criteria**

- [ ] Remote initialization with valid credentials stores encrypted authentication data
- [ ] Invalid credentials during initialization are rejected with clear error messages
- [ ] JWT tokens are managed automatically without manual intervention
- [ ] Query operations authenticate transparently using stored credentials
- [ ] Token refresh works automatically during query execution
- [ ] All authentication operations provide appropriate user feedback

[Conversation Reference: "Automatic authentication with stored credentials executes correctly"]

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Clean project directory without existing .code-indexer configuration
- Valid user credentials for test server
- Server configured for JWT authentication
- Network connectivity to authentication endpoints

**Test Environment Setup:**
1. Ensure clean project state (no existing .code-indexer directory)
2. Verify server authentication endpoints are accessible
3. Have both valid and invalid credentials ready
4. Prepare for token expiration testing (may require time wait)

**Security Validation:**
1. Inspect .code-indexer/.creds for encrypted storage (should be binary/encrypted)
2. Verify .code-indexer/.remote-config contains no plaintext passwords
3. Monitor network traffic for secure token transmission
4. Check system logs for credential exposure

**Post-Test Validation:**
1. Authentication state properly managed across sessions
2. No credential leakage in files or logs
3. Automatic token lifecycle working correctly
4. Stored credentials enable seamless query operations

[Conversation Reference: "Ensure encrypted credentials and JWT authentication"]
# Story 6.3: Real-World Error Scenarios

## 🎯 **Story Intent**

Validate error handling for actual production issues encountered during remote mode development, ensuring robust failure detection and recovery.

[Conversation Reference: "Test real failure scenarios encountered in development"]

## 📋 **Story Description**

**As a** Developer
**I want to** test error scenarios that actually occur in production
**So that** I can verify proper error handling and recovery mechanisms

## 🔧 **Test Procedures**

### Test 6.3.1: Resource Leak Detection
**Command to Execute:**
```bash
# This should NOT show resource leak warning (FIXED in health_checker.py)
cd /tmp/cidx-test  # Directory with remote configuration
python -m code_indexer.cli status
```

**Expected Results:**
- Status completes successfully
- NO "CIDXRemoteAPIClient was not properly closed" warning
- Proper resource cleanup in health checker with `await client.close()`
- Shows remote status with real server health checking

**Pass/Fail Criteria:**
- ✅ PASS: No resource leak warnings, real server status displayed
- ❌ FAIL: Resource leak warnings appear or fake status shown

### Test 6.3.2: Wrong API Endpoint Handling
**Test Description:** Verify health checker uses correct API endpoints (FIXED)

**Command to Monitor:**
```bash
# Monitor server logs while running status check
# In server terminal: watch for API calls
python -m code_indexer.cli status
```

**Expected Behavior:**
- Health checker calls `/api/repos` (correct endpoint, FIXED)
- Health checker does NOT call `/api/repositories` (wrong, returns 404)
- Server logs show correct endpoint usage without 404 errors
- Real server connectivity testing implemented

**Pass/Fail Criteria:**
- ✅ PASS: Uses correct API endpoints, no 404 errors, real health checking
- ❌ FAIL: Calls wrong endpoints, 404 errors in logs, or fake status

### Test 6.3.3: Mode Detection Failure Recovery
**Command to Execute:**
```bash
# Test with corrupted remote config
echo "invalid json" > .code-indexer/.remote-config
python -m code_indexer.cli status
```

**Expected Results:**
- Graceful handling of corrupted configuration
- Clear error message about configuration corruption
- Guidance for fixing the issue

**Pass/Fail Criteria:**
- ✅ PASS: Graceful error handling with clear guidance
- ❌ FAIL: Crash or unclear error messages

### Test 6.3.4: Credential Decryption Failure
**Command to Execute:**
```bash
# Test with corrupted credentials
echo "invalid_encrypted_data" > .code-indexer/.creds
python -m code_indexer.cli status
```

**Expected Results:**
- Credential decryption error detected
- Clear error message about credential corruption
- Suggestion to re-initialize remote mode

**Pass/Fail Criteria:**
- ✅ PASS: Clear credential error handling
- ❌ FAIL: Crash or misleading error messages

### Test 6.3.5: Server Down Graceful Handling
**Command to Execute:**
```bash
# Stop server, then test
# In server terminal: Ctrl+C
python -m code_indexer.cli status
```

**Expected Results:**
- Connection Health: ❌ Server Unreachable
- Clear error about server connectivity
- Actionable guidance for troubleshooting

**Pass/Fail Criteria:**
- ✅ PASS: Graceful server unreachable handling
- ❌ FAIL: Confusing errors or fake status data

## 📊 **Success Metrics**

- **Error Clarity**: All error messages provide actionable next steps
- **Resource Management**: No resource leaks in any scenario
- **Graceful Degradation**: System fails safely without corruption
- **Recovery Guidance**: Clear instructions for fixing issues

## 🎯 **Acceptance Criteria**

- [ ] Resource leak warnings eliminated in status command
- [ ] Correct API endpoints used by health checker
- [ ] Corrupted configuration handled gracefully
- [ ] Credential errors provide clear guidance
- [ ] Server unreachable scenarios handled properly
- [ ] All error messages are actionable and helpful

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Working remote mode configuration
- CIDX server available for testing
- Ability to modify configuration files
- Server log access for verification

**Test Environment Setup:**
1. Have working remote configuration as baseline
2. Backup original configuration files
3. Prepare invalid/corrupted test data
4. Monitor server logs during testing

**Real-World Context:**
These test scenarios are based on actual issues encountered:
- Resource leak warning during status checking
- Wrong API endpoint causing 404 errors
- Mode detection failing with pipx vs development versions
- Credential decryption failures with invalid padding

**Post-Test Cleanup:**
1. Restore original configuration files
2. Verify working state after each test
3. Clear any corrupted state before next test
4. Restart server if needed

[Conversation Reference: "Tests real failure scenarios encountered in development"]
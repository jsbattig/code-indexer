# Story 1.1: Remote Initialization Testing

## 🎯 **Story Intent**

Validate remote CIDX initialization commands and configuration setup through systematic manual testing procedures.

[Conversation Reference: "Remote initialization testing"]

## 📋 **Story Description**

**As a** Developer
**I want to** initialize CIDX in remote mode with proper configuration setup
**So that** I can connect to remote servers and execute queries

[Conversation Reference: "Each test story specifies exact python -m code_indexer.cli commands to execute"]

## 🔧 **Test Procedures**

### Test 1.1.1: Basic Remote Initialization (REAL SERVER)
**Prerequisites:**
```bash
# Start CIDX server (keep running in separate terminal)
cd /home/jsbattig/Dev/code-indexer
python -m code_indexer.server.main --port 8095
```

**Command to Execute:**
```bash
# Test in clean directory
mkdir -p /tmp/cidx-test && cd /tmp/cidx-test
python -m code_indexer.cli init --remote http://127.0.0.1:8095 --username admin --password admin
```

**Expected Results:**
- Command completes without errors (exit code 0)
- Configuration directory `.code-indexer/` is created
- Remote configuration file `.code-indexer/.remote-config` is created with encrypted credentials
- Credentials file `.code-indexer/.creds` is created with encrypted data
- Success message displays server connection confirmation

**Pass/Fail Criteria:**
- ✅ PASS: All expected results achieved, real server connection established
- ❌ FAIL: Any expected result missing or connection fails to real server

[Conversation Reference: "Clear pass/fail criteria for manual verification"]

### Test 1.1.2: Invalid Server URL Handling
**Command to Execute:**
```bash
python -m code_indexer.cli init --remote invalid://not-a-server --username testuser --password testpass
```

**Expected Results:**
- Command fails with clear error message
- No configuration files created
- Error message suggests checking server URL format
- Exit code is non-zero

**Pass/Fail Criteria:**
- ✅ PASS: Clear error message provided, no partial configuration
- ❌ FAIL: Unclear error or partial configuration created

### Test 1.1.3: Missing Credentials Prompt
**Command to Execute:**
```bash
python -m code_indexer.cli init --remote https://cidx-server.example.com
```

**Expected Results:**
- Command prompts for username input
- Command prompts for password input (masked)
- After providing credentials, initialization proceeds normally
- Configuration created with encrypted credentials

**Pass/Fail Criteria:**
- ✅ PASS: Interactive prompts work, credentials encrypted
- ❌ FAIL: No prompts or plaintext credential storage

### Test 1.1.4: Invalid Credentials Handling
**Command to Execute:**
```bash
python -m code_indexer.cli init --remote http://127.0.0.1:8095 --username invalid --password wrongpass
```

**Expected Results:**
- Authentication failure detected
- Clear error message about invalid credentials
- No configuration files created
- Suggestion to verify credentials provided

**Pass/Fail Criteria:**
- ✅ PASS: Authentication failure handled gracefully
- ❌ FAIL: Poor error handling or partial configuration

### Test 1.1.5: Status Command Real Server Health Checking
**Command to Execute:**
```bash
# After successful remote initialization
python -m code_indexer.cli status
```

**Expected Results:**
- Shows "🌐 Remote Code Indexer Status" (not local mode)
- Remote Server: 🌐 Connected with http://127.0.0.1:8095
- Connection Health: ✅ Healthy with real server verification
- NO "Repository Status" bullshit (removed from display)
- Real server reachability, auth validation, and repo access testing

**Pass/Fail Criteria:**
- ✅ PASS: Real remote status, server health verified, no fake data
- ❌ FAIL: Shows local mode or fake status information

### Test 1.1.6: CLI Binary vs Development Version Comparison
**Command to Execute:**
```bash
# Test pipx installed version (may be outdated)
which cidx
python -m code_indexer.cli status

# Test development version (current source)
python -m code_indexer.cli status
```

**Expected Results:**
- Development version shows real remote status
- Pipx version may show outdated behavior (local mode)
- Clear difference demonstrates version inconsistency

**Pass/Fail Criteria:**
- ✅ PASS: Development version works correctly, version difference identified
- ❌ FAIL: Both versions show same incorrect behavior

## 📊 **Success Metrics**

- **Execution Time**: Initialization completes within 60 seconds
- **Configuration Quality**: Proper .remote-config file created with encrypted credentials
- **Error Handling**: Clear, actionable error messages for all failure cases
- **User Experience**: Smooth initialization flow with appropriate feedback

[Conversation Reference: "Remote mode initialization completable in <60 seconds"]

## 🎯 **Acceptance Criteria**

- [ ] Basic remote initialization succeeds with valid parameters
- [ ] Invalid server URLs are handled with clear error messages
- [ ] Missing credentials trigger interactive prompts
- [ ] Invalid credentials are rejected with helpful error messages
- [ ] Configuration files are created only on successful initialization
- [ ] All error scenarios provide actionable next steps

[Conversation Reference: "Clear acceptance criteria for manual assessment"]

## 📝 **Manual Testing Notes**

**Prerequisites:**
- CIDX server running and accessible at test URL
- Valid test credentials available
- Network connectivity to target server
- Write permissions to current directory

**Test Environment Setup:**
1. Ensure clean directory (no existing .code-indexer/)
2. Verify server accessibility: `curl https://cidx-server.example.com/health`
3. Have valid and invalid credentials ready for testing

**Post-Test Validation:**
1. Check configuration file exists and contains encrypted data
2. Verify no plaintext passwords in any files
3. Confirm server connection established successfully

[Conversation Reference: "Manual execution environment with python -m code_indexer.cli CLI"]
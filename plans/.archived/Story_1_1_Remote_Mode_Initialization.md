# Story 1.1: Remote Mode Initialization with Valid Credentials

## 🎯 **Story Intent**

Validate the complete remote mode initialization process with valid credentials, ensuring proper configuration creation, credential encryption, and server validation.

## 📋 **User Story**

**As a** Developer
**I want to** initialize CIDX in remote mode with my team's server
**So that** I can immediately start querying shared code indexes without local setup

## 🔧 **Test Setup**

### Prerequisites
- Clean project directory without existing CIDX configuration
- Valid CIDX server URL and credentials
- Network connectivity to server
- Git repository with origin configured

### Test Environment
```bash
# Create test project
mkdir -p ~/test-remote-init
cd ~/test-remote-init
git init
git remote add origin https://github.com/company/test-repo.git

# Verify clean state
ls -la .code-indexer 2>/dev/null || echo "No existing config (expected)"
```

## 📊 **Test Scenarios**

### Scenario 1: Interactive Credential Input
**Test ID**: 1.1.1
**Priority**: Critical
**Duration**: 3 minutes

**Steps:**
1. Navigate to test project directory
2. Run: `cidx init --remote https://cidx.example.com`
3. When prompted, enter username: `testuser`
4. When prompted, enter password: `testpass123`
5. Wait for initialization to complete

**Expected Results:**
- ✅ Prompts for username appear
- ✅ Password input is masked (shows asterisks)
- ✅ "Validating server compatibility..." message appears
- ✅ "Remote mode initialized successfully" confirmation
- ✅ Command completes without errors

**Validation:**
```bash
# Verify configuration created
ls -la .code-indexer/.remote-config
# Should show file with 600 permissions

# Check file contents (should be encrypted)
cat .code-indexer/.remote-config | jq .
# Should show encrypted_credentials field, not plaintext
```

---

### Scenario 2: Command-Line Credential Input
**Test ID**: 1.1.2
**Priority**: High
**Duration**: 2 minutes

**Steps:**
1. Remove existing configuration: `rm -rf .code-indexer`
2. Run: `cidx init --remote https://cidx.example.com --username testuser --password testpass123`
3. Observe output

**Expected Results:**
- ✅ No interactive prompts appear
- ✅ Server validation performed
- ✅ Silent success (no output) or minimal confirmation
- ✅ Exit code 0

**Validation:**
```bash
echo $?  # Should be 0
cidx status | grep "Mode: Remote"  # Should show remote mode
```

---

### Scenario 3: Server Health Check Validation
**Test ID**: 1.1.3
**Priority**: High
**Duration**: 2 minutes

**Steps:**
1. Initialize with verbose flag: `cidx init --remote https://cidx.example.com --username testuser --password testpass123 --verbose`
2. Observe health check output

**Expected Results:**
- ✅ "Checking server health..." message
- ✅ "Server version: X.X.X" displayed
- ✅ "JWT authentication: enabled" confirmed
- ✅ "Required endpoints: available" verified
- ✅ Health check completes in <5 seconds

---

### Scenario 4: Credential Encryption Verification
**Test ID**: 1.1.4
**Priority**: Critical
**Duration**: 5 minutes

**Steps:**
1. After successful initialization, examine configuration file
2. Run encryption verification script:
```python
import json
import base64
from pathlib import Path

config = json.loads(Path(".code-indexer/.remote-config").read_text())
print(f"Encrypted: {'encrypted_credentials' in config}")
print(f"Salt present: {'salt' in config}")
print(f"Salt length: {len(base64.b64decode(config['salt']))}")
print(f"No plaintext: {'password' not in str(config).lower()}")
```

**Expected Results:**
- ✅ Encrypted: True
- ✅ Salt present: True
- ✅ Salt length: ≥16
- ✅ No plaintext: True

---

### Scenario 5: Configuration File Permissions
**Test ID**: 1.1.5
**Priority**: High
**Duration**: 1 minute

**Steps:**
1. Check file permissions: `ls -la .code-indexer/.remote-config`
2. Attempt to read as different user (if possible)

**Expected Results:**
- ✅ File permissions show `-rw-------` (600)
- ✅ Only owner can read/write
- ✅ Directory permissions appropriate

---

### Scenario 6: Invalid Server URL Handling
**Test ID**: 1.1.6
**Priority**: Medium
**Duration**: 2 minutes

**Steps:**
1. Attempt initialization with invalid URL: `cidx init --remote not-a-url --username test --password test`
2. Observe error message

**Expected Results:**
- ✅ Clear error: "Invalid server URL format"
- ✅ Suggests valid URL format
- ✅ No configuration created
- ✅ Exit code non-zero

---

### Scenario 7: Network Timeout Handling
**Test ID**: 1.1.7
**Priority**: Medium
**Duration**: 3 minutes

**Steps:**
1. Simulate network issue (firewall block or invalid host)
2. Run: `cidx init --remote https://unreachable.example.com --username test --password test`
3. Observe timeout behavior

**Expected Results:**
- ✅ Timeout occurs after reasonable time (5-10 seconds)
- ✅ Error message: "Unable to reach server"
- ✅ Suggests checking network connectivity
- ✅ No partial configuration created

## 🔍 **Validation Checklist**

### Security Validation
- [ ] Credentials never appear in plaintext in any output
- [ ] Password input is masked in terminal
- [ ] Configuration file has restricted permissions
- [ ] Encrypted credentials use strong encryption
- [ ] Salt is unique per installation

### Functional Validation
- [ ] Server connectivity verified before saving config
- [ ] API compatibility checked
- [ ] Configuration saved in correct location
- [ ] Subsequent commands recognize remote mode
- [ ] Status command shows correct information

### Error Handling Validation
- [ ] Invalid URLs rejected with clear message
- [ ] Network errors handled gracefully
- [ ] Authentication failures reported clearly
- [ ] No partial configurations on failure
- [ ] All errors provide actionable guidance

## 📈 **Performance Metrics**

| Metric | Target | Actual | Pass/Fail |
|--------|--------|--------|-----------|
| Init time (valid server) | <30s | | |
| Server health check | <5s | | |
| Credential encryption | <100ms | | |
| Total setup time | <60s | | |

## 🐛 **Issues Found**

| Issue | Severity | Description | Resolution |
|-------|----------|-------------|------------|
| | | | |

## ✅ **Sign-Off**

**Tester**: _____________________
**Date**: _____________________
**Test Result**: [ ] PASS [ ] FAIL [ ] BLOCKED
**Notes**: _____________________
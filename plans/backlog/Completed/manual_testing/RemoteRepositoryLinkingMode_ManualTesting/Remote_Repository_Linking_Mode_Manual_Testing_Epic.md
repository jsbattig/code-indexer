# 🧪 Remote Repository Linking Mode & Sync Enhancement - Comprehensive Manual Testing Epic

## 🎯 **Epic Intent**

Validate the complete Remote Repository Linking Mode functionality and CIDX Repository Sync Enhancement through comprehensive manual testing, ensuring production readiness for hybrid local/remote operation with team-shared indexing capabilities and seamless repository synchronization.

## 📋 **Epic Summary**

This epic provides exhaustive manual testing coverage for the Remote Repository Linking Mode and CIDX Repository Sync Enhancement, transforming CIDX from local-only to hybrid local/remote operation with comprehensive synchronization capabilities. Testing validates secure credential management, intelligent branch matching, transparent query execution, staleness detection, seamless mode switching, and full repository synchronization with semantic re-indexing.

The testing strategy covers functional validation, security verification, performance benchmarking, error recovery, cross-platform compatibility, and comprehensive sync workflow testing to ensure enterprise-grade quality before production deployment.

## 🏗️ **Testing Architecture Overview**

### Testing Environment Requirements

**Client-Side Setup:**
```
CIDX Client Test Environment
├── Multiple Test Projects (minimum 5)
│   ├── Project A: Fresh remote-only setup
│   ├── Project B: Local-to-remote migration
│   ├── Project C: Multi-branch repository
│   ├── Project D: Large repository for sync testing
│   └── Project E: Dirty working directory testing
├── Git Repositories
│   ├── Multiple branches (main, develop, feature/*)
│   ├── Varied file types and sizes
│   ├── Recent commit history
│   ├── Merge conflicts for testing
│   └── Large files for performance testing
└── Network Conditions
    ├── Stable connection scenarios
    ├── High latency simulation
    ├── Offline/disconnected testing
    └── Interrupted connection testing
```

**Server-Side Requirements:**
```
CIDX Server Infrastructure
├── JWT Authentication System
├── Multiple Golden Repositories
│   ├── Repository 1: Simple single-branch
│   ├── Repository 2: Complex multi-branch
│   ├── Repository 3: Large enterprise codebase
│   ├── Repository 4: Active development repo (frequent updates)
│   └── Repository 5: Repository with submodules
├── API Endpoints (Enhanced)
│   ├── Repository discovery by git URL
│   ├── Branch listing for golden repos
│   ├── Timestamp collection for staleness
│   ├── Sync job management (/sync, /jobs/*)
│   └── Progress tracking endpoints
├── Job Management System
│   ├── Job queue infrastructure
│   ├── Concurrent job handling
│   ├── Job persistence layer
│   └── Progress tracking system
└── Test User Accounts
    ├── Admin user with full privileges
    ├── Power users with repository access
    ├── Normal users with query permissions
    └── Sync users with job execution rights
```

### Testing Methodology

**Test Execution Phases:**
1. **Environment Validation**: Verify prerequisites and test infrastructure
2. **Feature Testing**: Systematic validation of each implemented feature
3. **Sync Testing**: Complete repository synchronization validation
4. **Integration Testing**: End-to-end workflow validation
5. **Security Testing**: Credential management and encryption validation
6. **Performance Testing**: Response time, sync performance, and staleness detection overhead
7. **Error Recovery**: Network failures, job failures, and graceful degradation
8. **User Experience**: CLI output quality, progress reporting, and error message clarity
9. **Concurrency Testing**: Multiple sync operations and job management

## 🎯 **Business Value Validation**

### Key Testing Objectives
- **Zero Setup Time**: Validate instant remote querying without local containers
- **Team Collaboration**: Verify shared indexing across multiple users
- **Repository Sync**: Validate complete git sync with semantic re-indexing
- **Job Management**: Verify reliable background job execution and tracking
- **Security Compliance**: Ensure encrypted credentials and JWT authentication
- **Performance Targets**: Confirm <2x query time vs local operation, sync within 2 minutes
- **User Experience**: Validate identical UX between local and remote modes
- **Progress Visibility**: Real-time progress reporting during sync operations

## 📊 **Success Metrics & Acceptance Criteria**

### Functional Metrics
- ✅ 100% command parity between local and remote modes
- ✅ >95% branch matching success rate
- ✅ Zero credential leakage between projects
- ✅ File-level staleness detection accuracy >99%
- ✅ 95% of syncs complete within 2 minutes
- ✅ 99.9% sync success rate for standard repositories
- ✅ Progress updates every 5% completion
- ✅ Support 10 concurrent syncs per user

### Non-Functional Metrics
- ✅ Remote initialization completes in <60 seconds
- ✅ Query response within 2x local query time
- ✅ Automatic JWT refresh prevents interruptions
- ✅ Network errors provide actionable guidance
- ✅ Sync job creation completes in <2 seconds
- ✅ Polling overhead <5% CPU usage
- ✅ Job state persists across server restarts
- ✅ Automatic retry on transient failures

---

## Prerequisites Setup

### Test Environment Preparation
- [ ] **Server Running**: CIDX server with JWT authentication on designated endpoint
- [ ] **API Version**: Server supports repository discovery, branch listing, timestamps
- [ ] **Golden Repositories**: At least 3 repositories indexed and available
- [ ] **Test Credentials**: Valid username/password for remote authentication
- [ ] **Git Repositories**: Local repos with matching remote golden repos
- [ ] **Network Access**: Connectivity to CIDX server verified

### Test Data Preparation
```bash
# Create test repositories with multiple branches
mkdir -p /tmp/test-remote-repo1
cd /tmp/test-remote-repo1
git init
git remote add origin https://github.com/test/repo1.git
echo "def main(): print('Main branch')" > main.py
git add . && git commit -m "Initial commit"
git checkout -b develop
echo "def develop(): print('Develop branch')" > develop.py
git add . && git commit -m "Add develop feature"
git checkout -b feature/test
echo "def feature(): print('Feature branch')" > feature.py
git add . && git commit -m "Add feature"
git checkout main

# Create second test repository
mkdir -p /tmp/test-remote-repo2
cd /tmp/test-remote-repo2
git init
git remote add origin https://github.com/test/repo2.git
# ... similar setup with different content

# Create third test repository for migration testing
mkdir -p /tmp/test-migration-repo
cd /tmp/test-migration-repo
cidx init  # Initialize in local mode first
cidx start
cidx index /path/to/code
# Repository ready for remote migration testing
```

---

## Feature 1: Remote Mode Initialization & Setup

### Story 1.1: Basic Remote Initialization
**As a** Developer
**I want to** initialize CIDX in remote mode
**So that** I can query team-shared indexes without local setup

#### Test Scenarios:
- [ ] **1.1.1** `cidx init --remote <server>` without credentials prompts for username/password
- [ ] **1.1.2** `cidx init --remote <server> --username <user> --password <pass>` succeeds silently
- [ ] **1.1.3** Initialize with invalid server URL returns clear error message
- [ ] **1.1.4** Initialize with invalid credentials returns authentication error
- [ ] **1.1.5** Configuration file `.code-indexer/.remote-config` created with encrypted credentials
- [ ] **1.1.6** Credentials encrypted using PBKDF2 with project-specific salt
- [ ] **1.1.7** Server health check performed during initialization
- [ ] **1.1.8** API version compatibility validated

**Expected Results:**
- Remote configuration created in `.code-indexer/.remote-config`
- Credentials stored encrypted, not plaintext
- Server connectivity verified before saving configuration
- Clear error messages for connection/authentication failures

### Story 1.2: Server Compatibility Validation
**As a** DevOps Engineer
**I want to** verify server compatibility during setup
**So that** I avoid runtime errors from incompatible API versions

#### Test Scenarios:
- [ ] **1.2.1** Initialize against compatible server version succeeds
- [ ] **1.2.2** Initialize against incompatible server shows version mismatch error
- [ ] **1.2.3** Server health endpoint validates JWT authentication capability
- [ ] **1.2.4** Missing required API endpoints detected during validation
- [ ] **1.2.5** Network timeout during validation handled gracefully
- [ ] **1.2.6** SSL certificate validation for HTTPS servers

**Pass/Fail Criteria:**
- Server compatibility check completes in <5 seconds
- Version mismatches prevent initialization with clear guidance
- Network errors provide retry suggestions

### Story 1.3: Multi-Project Credential Isolation
**As a** Team Lead
**I want to** maintain separate credentials per project
**So that** different projects can use different CIDX servers securely

#### Test Scenarios:
- [ ] **1.3.1** Project A credentials don't affect Project B
- [ ] **1.3.2** Each project directory has independent `.remote-config`
- [ ] **1.3.3** Credential encryption uses project-specific key derivation
- [ ] **1.3.4** Moving between projects switches credential context
- [ ] **1.3.5** Nested project directories use closest parent config
- [ ] **1.3.6** No credential leakage in environment variables or temp files

**Security Validation:**
- Each project's credentials independently encrypted
- No cross-contamination between project configurations
- Credentials never logged or displayed in plaintext

---

## Feature 2: Repository Discovery & Linking

### Story 2.1: Automatic Repository Discovery
**As a** Developer
**I want to** automatically link to matching remote repositories
**So that** I can start querying immediately without manual configuration

#### Test Scenarios:
- [ ] **2.1.1** Local repo with matching git origin URL auto-discovers remote golden repo
- [ ] **2.1.2** Discovery by git URL works with HTTPS URLs
- [ ] **2.1.3** Discovery by git URL works with SSH URLs
- [ ] **2.1.4** Discovery handles URL variations (trailing slash, .git suffix)
- [ ] **2.1.5** No matching repository returns informative message
- [ ] **2.1.6** Multiple matching repositories lists all options
- [ ] **2.1.7** Discovery completes within 2 seconds

**Expected Results:**
- Matching repositories automatically linked
- Clear feedback when no matches found
- URL normalization handles common variations

### Story 2.2: Intelligent Branch Matching
**As a** Developer
**I want to** automatically link to the most appropriate remote branch
**So that** my queries return relevant results for my current work

#### Test Scenarios:
- [ ] **2.2.1** Exact branch name match takes priority (main → main)
- [ ] **2.2.2** Git merge-base analysis finds best fallback branch
- [ ] **2.2.3** Feature branch falls back to develop if closer than main
- [ ] **2.2.4** Hotfix branch falls back to main/master appropriately
- [ ] **2.2.5** Orphaned branch triggers repository activation request
- [ ] **2.2.6** Branch matching explains selected branch in output
- [ ] **2.2.7** Manual branch override available via parameter

**Branch Matching Validation:**
```bash
# Test exact match
git checkout main
cidx query "test" --remote  # Should use remote main branch

# Test intelligent fallback
git checkout feature/new-ui
cidx query "test" --remote  # Should use develop or main based on merge-base

# Test orphaned branch
git checkout -b experimental
cidx query "test" --remote  # Should prompt for activation
```

### Story 2.3: Repository Activation Flow
**As a** Power User
**I want to** activate new repositories when no matches exist
**So that** I can index and share new codebases with my team

#### Test Scenarios:
- [ ] **2.3.1** Activation prompt appears for unmatched repositories
- [ ] **2.3.2** Activation request includes repository URL and branch
- [ ] **2.3.3** Server-side activation triggers indexing workflow
- [ ] **2.3.4** Activation status trackable via job system
- [ ] **2.3.5** Failed activation provides clear error reasons
- [ ] **2.3.6** Successful activation enables immediate querying

**Workflow Validation:**
- Clear activation prompt with confirmation
- Background job tracking for indexing progress
- Notification when repository becomes queryable

---

## Feature 3: Remote Query Execution

### Story 3.1: Transparent Remote Querying
**As a** Developer
**I want to** query remote repositories with identical commands
**So that** I don't need to learn new syntax for remote operation

#### Test Scenarios:
- [ ] **3.1.1** `cidx query "search term"` works identically in remote mode
- [ ] **3.1.2** Query parameters (--limit, --language, --path) function correctly
- [ ] **3.1.3** Query results format matches local mode exactly
- [ ] **3.1.4** Similarity scores consistent between local and remote
- [ ] **3.1.5** File paths in results relative to repository root
- [ ] **3.1.6** Code snippets properly formatted and highlighted
- [ ] **3.1.7** Query execution time reported accurately

**UX Validation:**
```bash
# Local mode query
cidx query "authentication function" --limit 5

# Remote mode query (identical command)
cidx query "authentication function" --limit 5

# Results should be visually identical except for execution time
```

### Story 3.2: JWT Authentication & Token Management
**As a** Security Engineer
**I want to** ensure secure authentication for all remote queries
**So that** unauthorized access is prevented

#### Test Scenarios:
- [ ] **3.2.1** First query triggers JWT token acquisition
- [ ] **3.2.2** Subsequent queries reuse cached token
- [ ] **3.2.3** Expired token triggers automatic re-authentication
- [ ] **3.2.4** Invalid credentials during refresh prompts for new login
- [ ] **3.2.5** Token stored securely in memory, not on disk
- [ ] **3.2.6** Token includes appropriate claims and expiration
- [ ] **3.2.7** Concurrent queries share token efficiently

**Security Testing:**
- Monitor network traffic for proper Authorization headers
- Verify token expiration handling (wait >10 minutes)
- Confirm no token leakage in logs or error messages

### Story 3.3: Network Resilience & Error Handling
**As a** Developer
**I want to** receive clear guidance when network issues occur
**So that** I can troubleshoot and recover quickly

#### Test Scenarios:
- [ ] **3.3.1** Network timeout provides retry suggestion
- [ ] **3.3.2** DNS resolution failure explains connectivity issue
- [ ] **3.3.3** Server 500 errors show "server temporarily unavailable"
- [ ] **3.3.4** Connection refused suggests checking server status
- [ ] **3.3.5** Partial response handling for interrupted queries
- [ ] **3.3.6** Automatic retry with exponential backoff
- [ ] **3.3.7** Offline mode detection with helpful message

**Network Testing Procedures:**
```bash
# Test timeout handling
# Configure firewall to drop packets
sudo iptables -A OUTPUT -d <server_ip> -j DROP
cidx query "test"  # Should timeout with clear message
sudo iptables -D OUTPUT -d <server_ip> -j DROP

# Test DNS failure
# Temporarily modify /etc/hosts with invalid entry
echo "127.0.0.1 cidx-server.example.com" >> /etc/hosts
cidx query "test"  # Should show DNS error
# Restore /etc/hosts

# Test server errors
# Stop server or trigger 500 error
cidx query "test"  # Should show server unavailable
```

---

## Feature 4: Staleness Detection & Indicators

### Story 4.1: File Timestamp Comparison
**As a** Developer
**I want to** know when remote results might be outdated
**So that** I can decide whether to trust the results

#### Test Scenarios:
- [ ] **4.1.1** Local file newer than remote shows staleness indicator
- [ ] **4.1.2** Remote file newer than local shows freshness indicator
- [ ] **4.1.3** Missing local file shows "remote-only" indicator
- [ ] **4.1.4** Timezone differences handled correctly (UTC normalization)
- [ ] **4.1.5** Staleness indicators appear in query results
- [ ] **4.1.6** Bulk staleness summary at end of results
- [ ] **4.1.7** Option to hide/show staleness indicators

**Staleness Testing:**
```bash
# Modify local file
echo "// New comment" >> src/main.py
touch src/main.py  # Update timestamp

# Query should show staleness
cidx query "main function"
# Result should show: ⚠️ (local file newer)

# Test timezone handling
TZ=UTC cidx query "test"
TZ=America/New_York cidx query "test"
# Results should be consistent
```

### Story 4.2: Visual Staleness Indicators
**As a** Developer
**I want to** quickly identify stale results visually
**So that** I can focus on fresh, relevant matches

#### Test Scenarios:
- [ ] **4.2.1** Fresh results show ✓ or green indicator
- [ ] **4.2.2** Stale results show ⚠️ or yellow indicator
- [ ] **4.2.3** Very stale results (>7 days) show ⛔ or red indicator
- [ ] **4.2.4** Remote-only results show 🔍 or blue indicator
- [ ] **4.2.5** Indicators align properly in terminal output
- [ ] **4.2.6** Color coding works in color-enabled terminals
- [ ] **4.2.7** Graceful fallback for non-color terminals

**Visual Validation:**
- Screenshot output with various staleness states
- Verify readability in different terminal themes
- Test with color-blind friendly indicators

### Story 4.3: Staleness in Local Mode
**As a** Developer
**I want to** see staleness information in local mode too
**So that** I know when my local index needs updating

#### Test Scenarios:
- [ ] **4.3.1** Local mode compares index time vs file modification
- [ ] **4.3.2** Modified files after indexing show stale indicator
- [ ] **4.3.3** Deleted files show "missing" indicator
- [ ] **4.3.4** New files show "not indexed" indicator
- [ ] **4.3.5** Staleness summary suggests re-indexing if needed
- [ ] **4.3.6** Performance impact of staleness checking <5%

---

## Feature 5: Credential Management & Security

### Story 5.1: Credential Rotation
**As a** Security Admin
**I want to** rotate credentials without losing configuration
**So that** I can maintain security compliance

#### Test Scenarios:
- [ ] **5.1.1** `cidx remote rotate-credentials` prompts for new password
- [ ] **5.1.2** Old credentials overwritten securely (memory cleared)
- [ ] **5.1.3** Configuration preserved except credentials
- [ ] **5.1.4** Next query uses new credentials automatically
- [ ] **5.1.5** Failed rotation rolls back to previous state
- [ ] **5.1.6** Audit log entry for credential rotation

**Rotation Testing:**
```bash
# Initial setup
cidx init --remote https://server --username user --password oldpass

# Rotate credentials
cidx remote rotate-credentials
# Enter new password when prompted

# Verify new credentials work
cidx query "test"  # Should succeed with new password

# Verify old credentials don't work
# Manually test with old password - should fail
```

### Story 5.2: Encryption Validation
**As a** Security Auditor
**I want to** verify credential encryption strength
**So that** I can confirm compliance with security standards

#### Test Scenarios:
- [ ] **5.2.1** PBKDF2 with 100,000+ iterations confirmed
- [ ] **5.2.2** Salt unique per project (not reused)
- [ ] **5.2.3** Encrypted data not reversible without password
- [ ] **5.2.4** Configuration file permissions set to 600 (user-only)
- [ ] **5.2.5** No credentials in process memory dumps
- [ ] **5.2.6** Credentials cleared from memory after use

**Security Validation:**
```bash
# Check file permissions
ls -la .code-indexer/.remote-config
# Should show -rw------- (600)

# Verify encryption (attempt to read)
cat .code-indexer/.remote-config
# Should show encrypted/base64 data, no plaintext

# Check for memory leaks
cidx query "test" &
PID=$!
sudo gcore $PID
strings core.$PID | grep -i password
# Should not find plaintext password
```

### Story 5.3: Multi-Project Isolation
**As a** Team Lead
**I want to** ensure project credentials remain isolated
**So that** different teams can't access each other's indexes

#### Test Scenarios:
- [ ] **5.3.1** Project A credentials don't work for Project B server
- [ ] **5.3.2** Copying config file to another project fails authentication
- [ ] **5.3.3** Each project's salt prevents credential reuse
- [ ] **5.3.4** No global credential storage or sharing
- [ ] **5.3.5** Environment variables don't leak between projects

---

## Feature 6: Mode Switching & Status

### Story 6.1: Mode Detection & Status
**As a** Developer
**I want to** know which mode CIDX is operating in
**So that** I understand where my queries are executed

#### Test Scenarios:
- [ ] **6.1.1** `cidx status` shows "Mode: Remote" when configured
- [ ] **6.1.2** `cidx status` shows "Mode: Local" for local setup
- [ ] **6.1.3** Status includes remote server URL (masked password)
- [ ] **6.1.4** Status shows linked repository information
- [ ] **6.1.5** Status indicates current branch mapping
- [ ] **6.1.6** Status shows token expiration time if available

**Status Output Validation:**
```
$ cidx status
CIDX Status:
  Mode: Remote
  Server: https://cidx.example.com
  User: developer1
  Repository: github.com/company/project
  Local Branch: feature/new-api
  Remote Branch: develop (via merge-base match)
  Token Valid: 8 minutes remaining
  Last Query: 2 minutes ago
```

### Story 6.2: Disabled Commands in Remote Mode
**As a** Developer
**I want to** receive clear messages for unavailable commands
**So that** I understand remote mode limitations

#### Test Scenarios:
- [ ] **6.2.1** `cidx start` shows "Not available in remote mode"
- [ ] **6.2.2** `cidx stop` shows "Not available in remote mode"
- [ ] **6.2.3** `cidx index` shows "Indexing managed by server"
- [ ] **6.2.4** Error messages suggest alternatives if applicable
- [ ] **6.2.5** Help text indicates remote-mode availability
- [ ] **6.2.6** Commands show [LOCAL ONLY] badge in help

### Story 6.3: Local to Remote Migration
**As a** Developer
**I want to** switch from local to remote mode
**So that** I can adopt team-shared indexing

#### Test Scenarios:
- [ ] **6.3.1** Existing local setup detected during remote init
- [ ] **6.3.2** Option to preserve or remove local containers
- [ ] **6.3.3** Configuration migration preserves settings
- [ ] **6.3.4** First remote query after migration succeeds
- [ ] **6.3.5** Local containers can be stopped/removed safely
- [ ] **6.3.6** Rollback to local mode possible if needed

---

## Feature 7: Performance & Optimization

### Story 7.1: Query Performance Benchmarking
**As a** Developer
**I want to** ensure remote queries perform acceptably
**So that** my development workflow remains efficient

#### Test Scenarios:
- [ ] **7.1.1** Simple query completes in <500ms
- [ ] **7.1.2** Complex query with filters completes in <2s
- [ ] **7.1.3** Large result set (100+ matches) handles efficiently
- [ ] **7.1.4** Performance consistent across multiple queries
- [ ] **7.1.5** Network latency shown separately from server time
- [ ] **7.1.6** Caching reduces repeat query time

**Performance Testing:**
```bash
# Benchmark simple query
time cidx query "function"

# Benchmark complex query
time cidx query "async database connection" --language python --limit 50

# Test caching effect
cidx query "test pattern"  # First query
cidx query "test pattern"  # Should be faster

# Measure network vs processing time
cidx query "test" --verbose
# Should show: Network: 50ms, Server: 100ms, Total: 150ms
```

### Story 7.2: Staleness Detection Performance
**As a** Developer
**I want** staleness checking to have minimal overhead
**So that** queries remain fast

#### Test Scenarios:
- [ ] **7.2.1** Staleness checking adds <10% to query time
- [ ] **7.2.2** Bulk file checking optimized for large results
- [ ] **7.2.3** Timestamp caching reduces repeated checks
- [ ] **7.2.4** Option to disable staleness checking for speed
- [ ] **7.2.5** Async staleness checking for large result sets

### Story 7.3: Token Management Efficiency
**As a** Developer
**I want** efficient token management
**So that** authentication doesn't slow down queries

#### Test Scenarios:
- [ ] **7.3.1** Token cached for entire session
- [ ] **7.3.2** Refresh happens proactively before expiration
- [ ] **7.3.3** Concurrent queries share single token
- [ ] **7.3.4** Token refresh doesn't block queries
- [ ] **7.3.5** Failed refresh triggers single re-auth

---

## Feature 8: Error Recovery & Diagnostics

### Story 8.1: Connection Error Recovery
**As a** Developer
**I want to** recover from connection errors automatically
**So that** temporary issues don't interrupt my work

#### Test Scenarios:
- [ ] **8.1.1** Automatic retry on connection timeout
- [ ] **8.1.2** Exponential backoff prevents server overload
- [ ] **8.1.3** Maximum retry limit prevents infinite loops
- [ ] **8.1.4** User can cancel retry with Ctrl+C
- [ ] **8.1.5** Successful retry shows attempt count
- [ ] **8.1.6** Final failure provides diagnostic steps

**Error Recovery Testing:**
```bash
# Simulate intermittent network
# Use network throttling tool
sudo tc qdisc add dev eth0 root netem loss 50%
cidx query "test"  # Should retry and possibly succeed
sudo tc qdisc del dev eth0 root

# Test retry cancellation
cidx query "test"  # During retry, press Ctrl+C
# Should exit cleanly with message
```

### Story 8.2: Authentication Error Handling
**As a** Developer
**I want** clear guidance for authentication issues
**So that** I can resolve credential problems quickly

#### Test Scenarios:
- [ ] **8.2.1** Invalid password prompts for re-entry
- [ ] **8.2.2** Account locked shows contact admin message
- [ ] **8.2.3** Expired account shows renewal instructions
- [ ] **8.2.4** Permission denied shows required role
- [ ] **8.2.5** Token corruption triggers re-authentication
- [ ] **8.2.6** Server auth failure vs client credential issue

### Story 8.3: Diagnostic Information
**As a** Support Engineer
**I want** comprehensive diagnostic information
**So that** I can troubleshoot user issues effectively

#### Test Scenarios:
- [ ] **8.3.1** `--verbose` flag shows detailed operation logs
- [ ] **8.3.2** `--debug` flag includes API request/response
- [ ] **8.3.3** Error messages include correlation IDs
- [ ] **8.3.4** Timing information for each operation phase
- [ ] **8.3.5** Network route tracing for connection issues
- [ ] **8.3.6** Configuration validation diagnostics

**Diagnostic Testing:**
```bash
# Verbose output
cidx query "test" --verbose
# Should show: Auth, Query, Network, Parse phases

# Debug output
cidx query "test" --debug
# Should show: Full HTTP request/response

# Diagnostic command
cidx diagnose --remote
# Should test: Connectivity, Auth, API access, Performance
```

---

## Feature 9: Cross-Platform Compatibility

### Story 9.1: Operating System Compatibility
**As a** Developer
**I want to** use remote mode on any operating system
**So that** team members can collaborate regardless of platform

#### Test Scenarios:
- [ ] **9.1.1** Linux: Ubuntu, Fedora, Arch Linux tested
- [ ] **9.1.2** macOS: Latest and previous version tested
- [ ] **9.1.3** Windows: WSL2 and native (if supported)
- [ ] **9.1.4** File path handling works cross-platform
- [ ] **9.1.5** Line ending differences handled correctly
- [ ] **9.1.6** Encryption works identically across platforms

**Platform Testing Matrix:**
| Platform | Init | Query | Staleness | Auth | Status |
|----------|------|-------|-----------|------|--------|
| Ubuntu 22.04 | | | | | |
| Fedora 38 | | | | | |
| macOS 14 | | | | | |
| macOS 13 | | | | | |
| WSL2 Ubuntu | | | | | |

### Story 9.2: Terminal Compatibility
**As a** Developer
**I want** proper display in different terminals
**So that** output is readable regardless of terminal choice

#### Test Scenarios:
- [ ] **9.2.1** Standard Linux terminal (gnome-terminal)
- [ ] **9.2.2** macOS Terminal.app
- [ ] **9.2.3** iTerm2
- [ ] **9.2.4** VS Code integrated terminal
- [ ] **9.2.5** tmux/screen sessions
- [ ] **9.2.6** SSH sessions with various clients
- [ ] **9.2.7** Unicode indicators display correctly

### Story 9.3: Git Integration Compatibility
**As a** Developer
**I want** remote mode to work with different git setups
**So that** I can use it with any repository configuration

#### Test Scenarios:
- [ ] **9.3.1** Standard git repositories
- [ ] **9.3.2** Git worktrees
- [ ] **9.3.3** Submodules
- [ ] **9.3.4** Shallow clones
- [ ] **9.3.5** Detached HEAD state
- [ ] **9.3.6** Multiple remotes

---

## Feature 10: Repository Sync Command & Options

### Story 10.1: Basic Sync Command
**As a** Developer
**I want to** sync my repository with a single command
**So that** I can update both git and semantic index effortlessly

#### Test Scenarios:
- [ ] **10.1.1** `cidx sync` syncs current branch with default settings
- [ ] **10.1.2** Sync command requires active remote configuration
- [ ] **10.1.3** Sync shows clear error if no linked repository
- [ ] **10.1.4** Sync command validates authentication before starting
- [ ] **10.1.5** Job ID returned immediately after sync initiation
- [ ] **10.1.6** Sync begins polling automatically after job creation
- [ ] **10.1.7** Default timeout of 300 seconds enforced
- [ ] **10.1.8** Ctrl+C cancels sync gracefully

**Expected Results:**
- Immediate job creation (<2 seconds)
- Clear job ID displayed
- Automatic polling begins
- Progress bar appears within 3 seconds

### Story 10.2: Sync Command Options
**As a** Power User
**I want to** control sync behavior with options
**So that** I can handle different synchronization scenarios

#### Test Scenarios:
- [ ] **10.2.1** `--full` flag forces complete re-indexing
- [ ] **10.2.2** `--branch <name>` syncs specific branch
- [ ] **10.2.3** `--timeout <seconds>` adjusts wait time
- [ ] **10.2.4** `--no-index` skips semantic indexing
- [ ] **10.2.5** `--strategy merge` uses merge strategy
- [ ] **10.2.6** `--strategy rebase` uses rebase strategy
- [ ] **10.2.7** `--quiet` suppresses progress output
- [ ] **10.2.8** `--json` outputs structured JSON results
- [ ] **10.2.9** Invalid options show helpful error messages
- [ ] **10.2.10** Option combinations work correctly

**Command Testing:**
```bash
# Test full re-indexing
cidx sync --full

# Test specific branch sync
cidx sync --branch develop

# Test with custom timeout
cidx sync --timeout 600

# Test merge strategies
cidx sync --strategy rebase

# Test quiet mode
cidx sync --quiet

# Test JSON output
cidx sync --json | jq '.status'
```

### Story 10.3: Multi-Repository Sync
**As a** Team Lead
**I want to** sync multiple repositories
**So that** I can update all projects efficiently

#### Test Scenarios:
- [ ] **10.3.1** Sequential syncs in different directories
- [ ] **10.3.2** Each project maintains independent sync state
- [ ] **10.3.3** Concurrent syncs from different terminals
- [ ] **10.3.4** Server enforces per-user concurrency limits
- [ ] **10.3.5** Queue position shown when limit exceeded
- [ ] **10.3.6** Failed sync doesn't affect other syncs

---

## Feature 11: Sync Job Management & Lifecycle

### Story 11.1: Job Creation & Initialization
**As a** Developer
**I want** reliable job creation
**So that** my sync operations are tracked properly

#### Test Scenarios:
- [ ] **11.1.1** Job created with unique ID
- [ ] **11.1.2** Job includes user ID and project ID
- [ ] **11.1.3** Job timestamp uses UTC
- [ ] **11.1.4** Job options preserved correctly
- [ ] **11.1.5** Job state starts as 'queued'
- [ ] **11.1.6** Job metadata includes git information
- [ ] **11.1.7** Duplicate job prevention within 30 seconds

**Job Creation Validation:**
```bash
# Start sync and capture job ID
cidx sync --json | jq '.jobId'

# Immediate duplicate rejected
cidx sync  # Should show "sync already in progress"
```

### Story 11.2: Job State Transitions
**As a** Developer
**I want** clear job state tracking
**So that** I understand sync progress

#### Test Scenarios:
- [ ] **11.2.1** State progression: queued → running → completed
- [ ] **11.2.2** Failed state includes error details
- [ ] **11.2.3** Cancelled state from user interruption
- [ ] **11.2.4** State timestamps tracked for each transition
- [ ] **11.2.5** State changes reflected in polling responses
- [ ] **11.2.6** Final states (completed/failed/cancelled) are terminal
- [ ] **11.2.7** Job history preserved for 7 days

**State Transition Testing:**
```bash
# Monitor state changes
cidx sync &
PID=$!
# Check /jobs/{id}/status endpoint multiple times
# Verify state progression
kill -INT $PID  # Test cancellation
```

### Story 11.3: Job Persistence & Recovery
**As a** System Administrator
**I want** jobs to survive server restarts
**So that** long-running syncs aren't lost

#### Test Scenarios:
- [ ] **11.3.1** Running jobs resume after server restart
- [ ] **11.3.2** Job state preserved in persistent storage
- [ ] **11.3.3** Progress checkpoint every 30 seconds
- [ ] **11.3.4** Partial completion tracked accurately
- [ ] **11.3.5** Recovery detects and handles corrupted state
- [ ] **11.3.6** Orphaned jobs cleaned up after 24 hours

---

## Feature 12: CLI Polling & Progress Reporting

### Story 12.1: Polling Loop Behavior
**As a** Developer
**I want** responsive polling
**So that** I see progress without overwhelming the server

#### Test Scenarios:
- [ ] **12.1.1** Polling starts immediately after job creation
- [ ] **12.1.2** 1-second interval between polls
- [ ] **12.1.3** Exponential backoff on network errors
- [ ] **12.1.4** Maximum 10 retries before failure
- [ ] **12.1.5** Polling stops on terminal states
- [ ] **12.1.6** Network usage <1KB per poll
- [ ] **12.1.7** CPU usage <5% during polling

**Polling Verification:**
```bash
# Monitor network traffic
tcpdump -i any host <server> &
cidx sync
# Verify 1-second intervals
# Check packet sizes
```

### Story 12.2: Progress Bar Display
**As a** Developer
**I want** visual progress indication
**So that** I know sync is progressing

#### Test Scenarios:
- [ ] **12.2.1** Progress bar appears within 3 seconds
- [ ] **12.2.2** Multi-phase progress shown clearly
- [ ] **12.2.3** Current phase labeled (Git/Index/Complete)
- [ ] **12.2.4** Percentage updates smoothly
- [ ] **12.2.5** ETA calculated and displayed
- [ ] **12.2.6** File count shown during indexing
- [ ] **12.2.7** Speed metrics (files/sec) displayed
- [ ] **12.2.8** Terminal width handled gracefully
- [ ] **12.2.9** Non-TTY fallback to text updates

**Progress Display Testing:**
```
Git Sync:    [████████████░░░░░░░░] 60% (2.5MB/4.2MB) ETA: 15s
Indexing:    [██░░░░░░░░░░░░░░░░░░] 10% (120/1200 files) 40 files/sec
Completing:  [████████████████████] 100% Done
```

### Story 12.3: Timeout & Cancellation
**As a** Developer
**I want** control over sync duration
**So that** I can manage long operations

#### Test Scenarios:
- [ ] **12.3.1** Default 300-second timeout enforced
- [ ] **12.3.2** Custom timeout via --timeout respected
- [ ] **12.3.3** Timeout triggers job cancellation
- [ ] **12.3.4** Ctrl+C sends cancel request to server
- [ ] **12.3.5** Graceful shutdown on SIGTERM
- [ ] **12.3.6** Cancel confirmation shown to user
- [ ] **12.3.7** Partial results preserved after cancel

---

## Feature 13: Git Sync Operations

### Story 13.1: Git Pull & Fetch
**As a** Developer
**I want** reliable git synchronization
**So that** my code stays current

#### Test Scenarios:
- [ ] **13.1.1** Clean working directory pulls successfully
- [ ] **13.1.2** Uncommitted changes handled appropriately
- [ ] **13.1.3** Fetch updates remote tracking branches
- [ ] **13.1.4** Fast-forward merges applied automatically
- [ ] **13.1.5** Non-fast-forward handled per strategy
- [ ] **13.1.6** Large repositories sync efficiently
- [ ] **13.1.7** Shallow clones handled correctly
- [ ] **13.1.8** Submodules updated if present

**Git Operation Testing:**
```bash
# Test with clean directory
git status  # Verify clean
cidx sync

# Test with uncommitted changes
echo "test" >> file.txt
cidx sync  # Should warn or handle

# Test large repository
cd /path/to/large-repo
time cidx sync --timeout 600
```

### Story 13.2: Merge Strategies
**As a** Developer
**I want** control over merge behavior
**So that** I can handle conflicts appropriately

#### Test Scenarios:
- [ ] **13.2.1** Default merge strategy preserves local changes
- [ ] **13.2.2** Rebase strategy creates linear history
- [ ] **13.2.3** 'Theirs' strategy accepts remote changes
- [ ] **13.2.4** 'Ours' strategy keeps local changes
- [ ] **13.2.5** Merge conflicts reported clearly
- [ ] **13.2.6** Conflict resolution guidance provided
- [ ] **13.2.7** Strategy persisted for future syncs

### Story 13.3: Change Detection
**As a** Developer
**I want** accurate change detection
**So that** only modified files are re-indexed

#### Test Scenarios:
- [ ] **13.3.1** Added files detected correctly
- [ ] **13.3.2** Modified files identified accurately
- [ ] **13.3.3** Deleted files tracked properly
- [ ] **13.3.4** Renamed files handled efficiently
- [ ] **13.3.5** Binary files excluded from indexing
- [ ] **13.3.6** Large files handled appropriately
- [ ] **13.3.7** .gitignore patterns respected

---

## Feature 14: Semantic Indexing Integration

### Story 14.1: Incremental Indexing
**As a** Developer
**I want** efficient incremental indexing
**So that** sync completes quickly

#### Test Scenarios:
- [ ] **14.1.1** Only changed files re-indexed
- [ ] **14.1.2** Dependency graph updated correctly
- [ ] **14.1.3** Vector embeddings regenerated
- [ ] **14.1.4** Index consistency maintained
- [ ] **14.1.5** Performance <10 seconds for <100 files
- [ ] **14.1.6** Memory usage stays below 1GB
- [ ] **14.1.7** Parallel processing utilized

**Indexing Performance Testing:**
```bash
# Modify specific files
touch src/file1.py src/file2.py
cidx sync
# Verify only 2 files indexed

# Large change set
find . -name "*.py" -exec touch {} \;
cidx sync --timeout 600
# Monitor indexing speed
```

### Story 14.2: Full Re-indexing
**As a** Developer
**I want** complete re-indexing option
**So that** I can rebuild the index when needed

#### Test Scenarios:
- [ ] **14.2.1** --full flag triggers complete re-index
- [ ] **14.2.2** All files processed regardless of timestamps
- [ ] **14.2.3** Old index entries removed
- [ ] **14.2.4** Progress shows total file count
- [ ] **14.2.5** Checkpoints every 100 files
- [ ] **14.2.6** Resumable after interruption
- [ ] **14.2.7** Index validation after completion

### Story 14.3: Index Validation
**As a** Developer
**I want** index integrity verification
**So that** queries return accurate results

#### Test Scenarios:
- [ ] **14.3.1** Checksum validation after sync
- [ ] **14.3.2** Vector dimension consistency
- [ ] **14.3.3** Metadata completeness verified
- [ ] **14.3.4** Orphaned entries cleaned up
- [ ] **14.3.5** Corruption detected and reported
- [ ] **14.3.6** Automatic repair attempted
- [ ] **14.3.7** Manual repair instructions provided

---

## Feature 15: Error Handling & Recovery

### Story 15.1: Network Error Handling
**As a** Developer
**I want** robust network error handling
**So that** temporary issues don't fail syncs

#### Test Scenarios:
- [ ] **15.1.1** Connection timeout triggers retry
- [ ] **15.1.2** DNS failure shows clear message
- [ ] **15.1.3** SSL errors provide certificate info
- [ ] **15.1.4** 500 errors trigger exponential backoff
- [ ] **15.1.5** 401 errors prompt re-authentication
- [ ] **15.1.6** Rate limiting handled gracefully
- [ ] **15.1.7** Partial response recovery
- [ ] **15.1.8** Network diagnosis suggestions

**Network Testing:**
```bash
# Simulate network issues
sudo tc qdisc add dev eth0 root netem delay 1000ms
cidx sync  # Should handle delay

# Test connection loss
sudo iptables -A OUTPUT -d <server> -j DROP
cidx sync  # Should retry and timeout
sudo iptables -D OUTPUT -d <server> -j DROP
```

### Story 15.2: Git Error Recovery
**As a** Developer
**I want** git error recovery
**So that** repository issues are handled

#### Test Scenarios:
- [ ] **15.2.1** Merge conflicts detected and reported
- [ ] **15.2.2** Lock file issues handled
- [ ] **15.2.3** Corrupted objects detected
- [ ] **15.2.4** Invalid credentials refreshed
- [ ] **15.2.5** Repository not found error
- [ ] **15.2.6** Permission denied handled
- [ ] **15.2.7** Disk space issues detected
- [ ] **15.2.8** Recovery suggestions provided

### Story 15.3: Job Failure Recovery
**As a** Developer
**I want** job failure recovery options
**So that** I can resolve sync issues

#### Test Scenarios:
- [ ] **15.3.1** Failed jobs show error details
- [ ] **15.3.2** Retry command available
- [ ] **15.3.3** Partial completion preserved
- [ ] **15.3.4** Diagnostic information collected
- [ ] **15.3.5** Support bundle generation
- [ ] **15.3.6** Automatic retry for transient errors
- [ ] **15.3.7** Manual intervention instructions
- [ ] **15.3.8** Rollback capability for index

---

## Feature 16: Performance & Optimization

### Story 16.1: Sync Performance Benchmarks
**As a** Developer
**I want** fast sync operations
**So that** my workflow isn't interrupted

#### Test Scenarios:
- [ ] **16.1.1** Small repo (<100 files) syncs in <30 seconds
- [ ] **16.1.2** Medium repo (1000 files) syncs in <2 minutes
- [ ] **16.1.3** Large repo (10000 files) syncs in <5 minutes
- [ ] **16.1.4** Incremental sync 10x faster than full
- [ ] **16.1.5** Network bandwidth efficiently utilized
- [ ] **16.1.6** CPU usage <50% during sync
- [ ] **16.1.7** Memory usage <2GB for large repos
- [ ] **16.1.8** Disk I/O optimized with batching

**Performance Testing Matrix:**
| Repository Size | Full Sync | Incremental | Network | CPU | Memory |
|----------------|-----------|-------------|---------|-----|--------|
| Small (100)    |           |             |         |     |        |
| Medium (1K)    |           |             |         |     |        |
| Large (10K)    |           |             |         |     |        |
| Huge (100K)    |           |             |         |     |        |

### Story 16.2: Concurrent Sync Performance
**As a** Team Lead
**I want** efficient concurrent syncs
**So that** multiple developers can sync simultaneously

#### Test Scenarios:
- [ ] **16.2.1** 2 concurrent syncs complete successfully
- [ ] **16.2.2** 5 concurrent syncs handled efficiently
- [ ] **16.2.3** 10 concurrent syncs respect limits
- [ ] **16.2.4** Queue management fair (FIFO)
- [ ] **16.2.5** Resource allocation balanced
- [ ] **16.2.6** No deadlocks or race conditions
- [ ] **16.2.7** Performance degradation <20% per sync

### Story 16.3: Progress Reporting Efficiency
**As a** Developer
**I want** efficient progress updates
**So that** monitoring doesn't impact performance

#### Test Scenarios:
- [ ] **16.3.1** Progress updates every 5% or 5 seconds
- [ ] **16.3.2** Update payload <1KB
- [ ] **16.3.3** Rendering <1% CPU usage
- [ ] **16.3.4** Terminal updates optimized
- [ ] **16.3.5** Network overhead <5%
- [ ] **16.3.6** Progress cache reduces queries
- [ ] **16.3.7** Batch updates for rapid changes

---

## Feature 17: Integration & End-to-End Workflows

### Story 17.1: Complete Developer Workflow with Sync
**As a** Developer
**I want to** complete my daily workflow using remote mode
**So that** I can validate real-world usage

#### Test Scenarios:
- [ ] **17.1.1** Morning setup: Init → Status → Sync → First query
- [ ] **17.1.2** Feature development: Branch switch → Sync → Multiple queries
- [ ] **17.1.3** Code review: Sync different branches → Query for comparison
- [ ] **17.1.4** Team updates: Pull changes → Sync → Verify index updates
- [ ] **17.1.5** Debugging: Sync latest → Intensive querying
- [ ] **17.1.6** End of day: Final sync → Status check
- [ ] **17.1.7** Full day without re-authentication issues
- [ ] **17.1.8** Multiple syncs throughout the day

**Daily Workflow Simulation:**
```bash
# Morning (9 AM)
cd ~/projects/backend
cidx init --remote https://cidx.company.com --username dev1 --password pass
cidx sync  # Get latest changes
cidx status
cidx query "main application entry"

# Team updates (10 AM)
git pull origin develop
cidx sync --branch develop  # Sync team changes
cidx query "recent changes" --limit 20

# Feature work (11 AM - 12 PM)
git checkout feature/new-api
cidx sync  # Sync feature branch
cidx query "REST endpoint handlers"
cidx query "authentication middleware"

# After lunch sync (1 PM)
cidx sync  # Get any morning updates
cidx query "database connection" --language python

# Code review (2 PM)
git checkout develop
cidx sync --full  # Full re-index for thorough review
cidx query "recently modified functions" --limit 20

# Debugging (3 PM - 5 PM)
cidx sync  # Ensure latest code
cidx query "error handling"
cidx query "try catch patterns"

# End of day (5 PM)
cidx sync --quiet  # Final sync
cidx status  # Verify token still valid
```

### Story 17.2: Team Collaboration Workflow with Sync
**As a** Team Lead
**I want** multiple developers to share the same indexes
**So that** we have consistent search results across the team

#### Test Scenarios:
- [ ] **17.2.1** Developer A syncs, then B syncs same repository
- [ ] **17.2.2** Both developers see identical index after sync
- [ ] **17.2.3** Concurrent syncs by different team members
- [ ] **17.2.4** Changes by A visible to B after B syncs
- [ ] **17.2.5** Different branches sync independently
- [ ] **17.2.6** New team member: Init → Sync → Query workflow
- [ ] **17.2.7** Repository updates propagate to all users
- [ ] **17.2.8** Sync conflicts handled gracefully

**Multi-User Testing:**
```bash
# User A makes changes
git add new-feature.py
git commit -m "Add feature"
git push origin develop
cidx sync  # Sync changes to server

# User B gets updates
cidx sync  # Pull A's changes
cidx query "new-feature"  # Should find A's code

# Concurrent sync testing
# User A terminal 1
cidx sync --full &

# User B terminal 2 (simultaneously)
cidx sync --branch develop &

# Both should complete successfully
wait
```

### Story 17.3: Migration Scenarios with Sync
**As a** DevOps Engineer
**I want to** migrate teams from local to remote mode
**So that** we can adopt shared indexing incrementally

#### Test Scenarios:
- [ ] **17.3.1** Local to remote migration with sync capability
- [ ] **17.3.2** First sync after migration indexes everything
- [ ] **17.3.3** Team migration with sync verification
- [ ] **17.3.4** Sync performance comparison vs local indexing
- [ ] **17.3.5** Rollback preserves sync history
- [ ] **17.3.6** Configuration migration includes sync settings
- [ ] **17.3.7** Training includes sync workflow
- [ ] **17.3.8** Hybrid mode: local index + remote sync

### Story 17.4: Disaster Recovery with Sync
**As a** DevOps Engineer
**I want to** handle server failures gracefully
**So that** developers aren't blocked during outages

#### Test Scenarios:
- [ ] **17.4.1** Server fails during sync operation
- [ ] **17.4.2** Sync resumes from checkpoint after recovery
- [ ] **17.4.3** Partial sync results preserved
- [ ] **17.4.4** Index rollback on corrupted sync
- [ ] **17.4.5** Job cleanup after server restart
- [ ] **17.4.6** Sync queue recovery and reprocessing
- [ ] **17.4.7** Data consistency validation after recovery
- [ ] **17.4.8** Manual sync recovery procedures

---

## Performance Benchmarks & Acceptance Criteria

### Performance Requirements
| Metric | Target | Acceptable | Actual | Status |
|--------|--------|------------|--------|--------|
| Remote init time | <30s | <60s | | |
| Simple query response | <200ms | <500ms | | |
| Complex query response | <1s | <2s | | |
| Staleness check overhead | <5% | <10% | | |
| Token refresh time | <100ms | <200ms | | |
| Network retry delay | Exponential | Max 30s | | |
| Memory usage increase | <10MB | <50MB | | |
| Sync job creation | <2s | <5s | | |
| Small repo sync | <30s | <60s | | |
| Medium repo sync | <2min | <3min | | |
| Large repo sync | <5min | <10min | | |
| Polling overhead | <5% CPU | <10% CPU | | |
| Progress update frequency | 5% or 5s | 10% or 10s | | |
| Concurrent sync limit | 10/user | 5/user | | |

### Security Requirements
| Requirement | Validation Method | Status |
|-------------|------------------|---------|
| Credentials encrypted | File inspection | |
| PBKDF2 iterations ≥100k | Code review | |
| Project isolation | Multi-project test | |
| Token in memory only | Memory dump analysis | |
| No plaintext logging | Log analysis | |
| Secure credential rotation | Rotation test | |
| Job authorization | User permission test | |
| Sync isolation | Multi-user test | |
| Git credentials secure | Credential audit | |

### User Experience Requirements
| Aspect | Requirement | Status |
|--------|------------|--------|
| Command parity | 100% identical syntax | |
| Error messages | Clear and actionable | |
| Setup complexity | <5 commands | |
| Help documentation | Complete and accurate | |
| Status information | Comprehensive | |
| Performance feedback | Real-time progress | |
| Sync command simplicity | Single command | |
| Progress visibility | Multi-phase display | |
| Job management | Transparent to user | |
| Recovery guidance | Step-by-step | |

---

## Issue Tracking

| Test ID | Issue Description | Severity | Status | Resolution |
|---------|------------------|----------|--------|------------|
| | | | | |

---

## Testing Summary

### Execution Summary
- **Total Test Scenarios**: 384 (234 original + 150 sync)
- **Executed**: ___
- **Passed**: ___
- **Failed**: ___
- **Blocked**: ___
- **Success Rate**: ___%

### Feature Coverage
| Feature | Tests | Passed | Failed | Coverage |
|---------|-------|--------|--------|----------|
| Remote Init & Setup | 21 | | | % |
| Repository Discovery | 20 | | | % |
| Remote Query | 21 | | | % |
| Staleness Detection | 19 | | | % |
| Credential Management | 17 | | | % |
| Mode Switching | 17 | | | % |
| Performance | 14 | | | % |
| Error Recovery | 18 | | | % |
| Cross-Platform | 19 | | | % |
| **Sync Enhancement Features** | | | | |
| Repository Sync Command | 29 | | | % |
| Job Management & Lifecycle | 20 | | | % |
| CLI Polling & Progress | 24 | | | % |
| Git Sync Operations | 22 | | | % |
| Semantic Indexing Integration | 21 | | | % |
| Error Handling & Recovery | 24 | | | % |
| Performance & Optimization | 22 | | | % |
| Integration & End-to-End | 32 | | | % |
| **TOTAL** | **360** | | | % |

### Critical Issues
1.
2.
3.

### Security Findings
1.
2.
3.

### Performance Results
1.
2.
3.

### Recommendations
1.
2.
3.
4.
5.

---

## Sign-Off

### Testing Team
- **Lead Tester**: _____________________
- **Security Reviewer**: _____________________
- **Performance Analyst**: _____________________
- **UX Validator**: _____________________

### Management Approval
- **QA Manager**: _____________________
- **Product Owner**: _____________________
- **Engineering Lead**: _____________________

### Final Verdict
- [ ] **APPROVED FOR PRODUCTION** - All critical tests passed
- [ ] **CONDITIONAL APPROVAL** - Minor issues documented
- [ ] **REQUIRES FIXES** - Critical issues must be resolved
- [ ] **REJECTED** - Major functionality gaps

**Testing Date**: _____________________
**Version Tested**: _____________________
**Environment**: _____________________

---

## Appendix A: Test Environment Setup

### Server Configuration
```yaml
server:
  url: https://cidx-server.example.com
  version: 4.3.0
  auth: JWT
  repositories:
    - name: backend-api
      url: https://github.com/company/backend
      branches: [main, develop, staging]
    - name: frontend-ui
      url: https://github.com/company/frontend
      branches: [main, develop, feature/*]
    - name: shared-libs
      url: https://github.com/company/libs
      branches: [main, release/*]
```

### Client Test Projects
```bash
# Project structure for testing
/test-environment/
├── project-a/          # Fresh remote setup
│   ├── .git/
│   └── src/
├── project-b/          # Migration from local
│   ├── .git/
│   ├── .code-indexer/  # Existing local config
│   └── src/
└── project-c/          # Multi-branch testing
    ├── .git/
    │   ├── refs/heads/main
    │   ├── refs/heads/develop
    │   └── refs/heads/feature/test
    └── src/
```

### Network Simulation Tools
```bash
# Install network simulation tools
sudo apt-get install tc netem

# Simulate various network conditions
# High latency
sudo tc qdisc add dev eth0 root netem delay 200ms

# Packet loss
sudo tc qdisc add dev eth0 root netem loss 10%

# Bandwidth limitation
sudo tc qdisc add dev eth0 root tbf rate 1mbit burst 32kbit latency 400ms

# Remove all rules
sudo tc qdisc del dev eth0 root
```

---

## Appendix B: Security Testing Procedures

### Credential Encryption Validation
```python
# Script to verify PBKDF2 implementation
import hashlib
import base64
from pathlib import Path
import json

def verify_encryption():
    config_path = Path(".code-indexer/.remote-config")
    with open(config_path) as f:
        config = json.load(f)

    # Check for plaintext
    assert "password" not in str(config).lower()

    # Verify encrypted field exists
    assert "encrypted_credentials" in config

    # Verify salt uniqueness
    salt = config.get("salt")
    assert salt and len(base64.b64decode(salt)) >= 16

    print("✅ Encryption validation passed")

verify_encryption()
```

### Token Security Testing
```bash
# Monitor token handling
strace -e trace=open,read,write -o trace.log cidx query "test"
grep -i "bearer\|token\|jwt" trace.log
# Should only appear in network calls, not file operations

# Check for token in environment
env | grep -i token
# Should return nothing

# Verify token expiration
cidx query "test"
sleep 600  # Wait for token expiration (10 minutes)
cidx query "test"  # Should re-authenticate
```

---

## Appendix C: Sync Testing Environment Setup

### Repository Preparation for Sync Testing

```bash
#!/bin/bash
# prepare_sync_test_repos.sh

# Create multiple test scenarios
echo "Setting up sync test repositories..."

# 1. Clean repository for basic sync
mkdir -p /tmp/sync-test-clean
cd /tmp/sync-test-clean
git init
git remote add origin https://github.com/test/sync-clean.git
echo "# Clean Repo" > README.md
git add . && git commit -m "Initial commit"

# 2. Repository with uncommitted changes
mkdir -p /tmp/sync-test-dirty
cd /tmp/sync-test-dirty
git init
git remote add origin https://github.com/test/sync-dirty.git
echo "# Dirty Repo" > README.md
git add . && git commit -m "Initial commit"
echo "Uncommitted change" >> README.md
echo "new_file.txt" > new_file.txt

# 3. Repository with merge conflicts
mkdir -p /tmp/sync-test-conflicts
cd /tmp/sync-test-conflicts
git init
git remote add origin https://github.com/test/sync-conflicts.git
echo "Line 1" > conflict.txt
git add . && git commit -m "Initial commit"
git checkout -b feature
echo "Feature change" >> conflict.txt
git add . && git commit -m "Feature change"
git checkout main
echo "Main change" >> conflict.txt
git add . && git commit -m "Main change"

# 4. Large repository simulation
mkdir -p /tmp/sync-test-large
cd /tmp/sync-test-large
git init
git remote add origin https://github.com/test/sync-large.git
# Generate 10,000 files
for i in {1..10000}; do
    mkdir -p "src/module_$((i/100))"
    echo "def function_$i(): return $i" > "src/module_$((i/100))/file_$i.py"
done
git add .
git commit -m "Large repository with 10k files"

# 5. Repository with submodules
mkdir -p /tmp/sync-test-submodules
cd /tmp/sync-test-submodules
git init
git remote add origin https://github.com/test/sync-submodules.git
git submodule add https://github.com/test/submodule1.git lib/submodule1
git submodule add https://github.com/test/submodule2.git lib/submodule2
git commit -m "Add submodules"

echo "Sync test repositories prepared!"
```

### Job Testing Utilities

```python
#!/usr/bin/env python3
# job_monitor.py - Monitor sync job lifecycle

import requests
import time
import json
from datetime import datetime

class SyncJobMonitor:
    def __init__(self, server_url, token):
        self.server = server_url
        self.headers = {"Authorization": f"Bearer {token}"}

    def start_sync(self, options={}):
        """Start a new sync job"""
        response = requests.post(
            f"{self.server}/api/sync",
            json=options,
            headers=self.headers
        )
        return response.json()["jobId"]

    def monitor_job(self, job_id):
        """Monitor job progress until completion"""
        states = []
        start_time = datetime.now()

        while True:
            response = requests.get(
                f"{self.server}/api/jobs/{job_id}/status",
                headers=self.headers
            )
            status = response.json()

            states.append({
                "time": (datetime.now() - start_time).total_seconds(),
                "state": status["state"],
                "progress": status.get("progress", 0),
                "phase": status.get("phase", "unknown")
            })

            print(f"[{states[-1]['time']:.1f}s] "
                  f"State: {status['state']} "
                  f"Phase: {status.get('phase', 'N/A')} "
                  f"Progress: {status.get('progress', 0)}%")

            if status["state"] in ["completed", "failed", "cancelled"]:
                break

            time.sleep(1)

        return states

    def test_concurrent_jobs(self, count=5):
        """Test multiple concurrent sync jobs"""
        job_ids = []

        # Start multiple jobs
        for i in range(count):
            job_id = self.start_sync({"branch": f"test-{i}"})
            job_ids.append(job_id)
            print(f"Started job {i+1}: {job_id}")

        # Monitor all jobs
        results = {}
        for job_id in job_ids:
            print(f"\nMonitoring job: {job_id}")
            results[job_id] = self.monitor_job(job_id)

        return results

# Usage example
if __name__ == "__main__":
    monitor = SyncJobMonitor(
        "https://cidx-server.example.com",
        "your-jwt-token"
    )

    # Test single sync
    job_id = monitor.start_sync({"full": True})
    states = monitor.monitor_job(job_id)

    # Analyze job lifecycle
    print("\nJob Lifecycle Analysis:")
    for state in states:
        print(f"  {state['time']:.1f}s: {state['state']} "
              f"({state['phase']}) - {state['progress']}%")
```

### Network Simulation for Sync Testing

```bash
#!/bin/bash
# network_sync_test.sh - Test sync under various network conditions

echo "Network Simulation for Sync Testing"

# Function to run sync with network condition
test_sync_with_network() {
    local condition=$1
    local description=$2

    echo -e "\n========================================="
    echo "Testing: $description"
    echo "========================================="

    # Apply network condition
    eval "$condition"

    # Run sync and capture metrics
    start_time=$(date +%s)
    cidx sync --timeout 600 2>&1 | tee /tmp/sync_${description// /_}.log
    exit_code=$?
    end_time=$(date +%s)
    duration=$((end_time - start_time))

    # Clean network rules
    sudo tc qdisc del dev eth0 root 2>/dev/null

    echo "Result: Exit code=$exit_code, Duration=${duration}s"

    return $exit_code
}

# Test scenarios
test_sync_with_network \
    "sudo tc qdisc add dev eth0 root netem delay 50ms" \
    "Low latency (50ms)"

test_sync_with_network \
    "sudo tc qdisc add dev eth0 root netem delay 200ms" \
    "High latency (200ms)"

test_sync_with_network \
    "sudo tc qdisc add dev eth0 root netem loss 1%" \
    "1% packet loss"

test_sync_with_network \
    "sudo tc qdisc add dev eth0 root netem loss 5%" \
    "5% packet loss"

test_sync_with_network \
    "sudo tc qdisc add dev eth0 root tbf rate 1mbit burst 32kbit latency 400ms" \
    "Limited bandwidth (1Mbps)"

test_sync_with_network \
    "sudo tc qdisc add dev eth0 root netem delay 100ms 50ms distribution normal" \
    "Variable latency (100ms ± 50ms)"

# Summary report
echo -e "\n========================================="
echo "Network Simulation Summary"
echo "========================================="
grep "Result:" /tmp/sync_*.log
```

---

## Appendix D: Performance Testing Scripts

### Query Performance Benchmark
```bash
#!/bin/bash
# benchmark_queries.sh

echo "Starting performance benchmark..."

# Simple queries
for i in {1..10}; do
    time -p cidx query "function" 2>&1 | grep real
done | awk '{sum+=$2} END {printf "Simple query avg: %.3fs\n", sum/NR}'

# Complex queries
for i in {1..10}; do
    time -p cidx query "async database connection" --language python --limit 50 2>&1 | grep real
done | awk '{sum+=$2} END {printf "Complex query avg: %.3fs\n", sum/NR}'

# Staleness checking overhead
echo "Testing staleness overhead..."
time cidx query "test pattern" --no-staleness
time cidx query "test pattern"  # With staleness
```

### Load Testing
```bash
#!/bin/bash
# load_test.sh

# Concurrent queries from multiple processes
for i in {1..10}; do
    (cidx query "test pattern $i" &)
done
wait

echo "Load test complete"
```

---

## Appendix E: Sync-Specific Testing Procedures

### Sync Progress Validation

```bash
#!/bin/bash
# validate_sync_progress.sh - Validate progress reporting accuracy

echo "Sync Progress Validation Test"

# Function to parse progress from output
parse_progress() {
    local output=$1
    echo "$output" | grep -oE '[0-9]+%' | tail -1 | tr -d '%'
}

# Test progress reporting accuracy
test_progress_accuracy() {
    local test_name=$1
    local sync_options=$2

    echo -e "\n=== Testing: $test_name ==="

    # Capture sync output
    cidx sync $sync_options 2>&1 | tee /tmp/sync_progress.log &
    SYNC_PID=$!

    # Monitor progress updates
    last_progress=0
    progress_updates=0

    while kill -0 $SYNC_PID 2>/dev/null; do
        current_progress=$(parse_progress "$(tail -5 /tmp/sync_progress.log)")

        if [ ! -z "$current_progress" ] && [ "$current_progress" -gt "$last_progress" ]; then
            echo "Progress: $last_progress% -> $current_progress%"
            last_progress=$current_progress
            ((progress_updates++))
        fi

        sleep 1
    done

    wait $SYNC_PID
    exit_code=$?

    echo "Total progress updates: $progress_updates"
    echo "Final progress: $last_progress%"
    echo "Exit code: $exit_code"

    # Validate progress reached 100% on success
    if [ $exit_code -eq 0 ] && [ "$last_progress" -ne 100 ]; then
        echo "WARNING: Sync succeeded but progress didn't reach 100%"
    fi
}

# Run tests
test_progress_accuracy "Basic sync" ""
test_progress_accuracy "Full sync" "--full"
test_progress_accuracy "Quiet sync" "--quiet"
```

### Concurrent Sync Testing

```bash
#!/bin/bash
# concurrent_sync_test.sh - Test multiple simultaneous sync operations

echo "Concurrent Sync Testing"

# Function to run sync in background
run_sync() {
    local project_dir=$1
    local sync_id=$2

    cd "$project_dir"
    echo "[Sync $sync_id] Starting in $project_dir"

    start_time=$(date +%s)
    cidx sync --json 2>&1 | tee "/tmp/sync_${sync_id}.log"
    exit_code=$?
    end_time=$(date +%s)
    duration=$((end_time - start_time))

    echo "[Sync $sync_id] Completed: exit=$exit_code, duration=${duration}s"
    return $exit_code
}

# Create test projects
for i in {1..5}; do
    mkdir -p "/tmp/concurrent_test_$i"
    cd "/tmp/concurrent_test_$i"
    cidx init --remote https://server --username test --password test
done

# Start concurrent syncs
echo "Starting 5 concurrent sync operations..."
for i in {1..5}; do
    run_sync "/tmp/concurrent_test_$i" $i &
    PIDS[$i]=$!
done

# Wait for all syncs to complete
echo "Waiting for all syncs to complete..."
for i in {1..5}; do
    wait ${PIDS[$i]}
    EXIT_CODES[$i]=$?
done

# Analyze results
echo -e "\n=== Concurrent Sync Results ==="
success_count=0
for i in {1..5}; do
    if [ ${EXIT_CODES[$i]} -eq 0 ]; then
        echo "Sync $i: SUCCESS"
        ((success_count++))
    else
        echo "Sync $i: FAILED (exit code: ${EXIT_CODES[$i]})"
    fi
done

echo -e "\nTotal: $success_count/5 successful"

# Check for job queue behavior
echo -e "\n=== Job Queue Analysis ==="
for i in {1..5}; do
    grep -E "queued|waiting" "/tmp/sync_${i}.log" && echo "Sync $i was queued"
done
```

### Sync Failure Recovery Testing

```python
#!/usr/bin/env python3
# sync_failure_recovery.py - Test sync failure recovery mechanisms

import subprocess
import time
import json
import signal
import os

class SyncFailureTest:
    def __init__(self):
        self.test_results = []

    def run_test(self, test_name, setup_fn, teardown_fn=None):
        """Run a single failure recovery test"""
        print(f"\n=== Testing: {test_name} ===")

        try:
            # Setup failure condition
            setup_fn()

            # Attempt sync
            start_time = time.time()
            result = subprocess.run(
                ["cidx", "sync", "--timeout", "30", "--json"],
                capture_output=True,
                text=True
            )
            duration = time.time() - start_time

            # Parse output
            try:
                output = json.loads(result.stdout)
                status = output.get("status", "unknown")
                error = output.get("error", None)
            except:
                status = "parse_error"
                error = result.stderr

            self.test_results.append({
                "test": test_name,
                "exit_code": result.returncode,
                "status": status,
                "error": error,
                "duration": duration
            })

            print(f"Result: exit_code={result.returncode}, "
                  f"status={status}, duration={duration:.1f}s")

        finally:
            # Cleanup
            if teardown_fn:
                teardown_fn()

    def test_network_interruption(self):
        """Test sync recovery from network interruption"""
        def setup():
            # Start sync in background
            self.sync_proc = subprocess.Popen(
                ["cidx", "sync"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(5)  # Let sync start

            # Simulate network interruption
            os.system("sudo iptables -A OUTPUT -d cidx-server -j DROP")
            time.sleep(10)

            # Restore network
            os.system("sudo iptables -D OUTPUT -d cidx-server -j DROP")

        def teardown():
            if hasattr(self, 'sync_proc'):
                self.sync_proc.terminate()
                self.sync_proc.wait()

        self.run_test("Network Interruption Recovery", setup, teardown)

    def test_server_timeout(self):
        """Test sync behavior when server times out"""
        def setup():
            # Configure very short timeout
            pass

        self.run_test("Server Timeout Handling", setup)

    def test_auth_expiry(self):
        """Test sync with expired authentication"""
        def setup():
            # Wait for token to expire (if possible)
            # Or manually corrupt token
            pass

        self.run_test("Authentication Expiry", setup)

    def test_disk_space(self):
        """Test sync with insufficient disk space"""
        def setup():
            # Fill up disk to near capacity
            os.system("dd if=/dev/zero of=/tmp/large_file bs=1M count=10000")

        def teardown():
            os.system("rm -f /tmp/large_file")

        self.run_test("Insufficient Disk Space", setup, teardown)

    def generate_report(self):
        """Generate test report"""
        print("\n" + "="*60)
        print("SYNC FAILURE RECOVERY TEST REPORT")
        print("="*60)

        for result in self.test_results:
            print(f"\nTest: {result['test']}")
            print(f"  Exit Code: {result['exit_code']}")
            print(f"  Status: {result['status']}")
            print(f"  Duration: {result['duration']:.1f}s")
            if result['error']:
                print(f"  Error: {result['error']}")

        # Summary
        passed = sum(1 for r in self.test_results if r['exit_code'] == 0)
        total = len(self.test_results)
        print(f"\n{'='*60}")
        print(f"Summary: {passed}/{total} tests handled gracefully")

if __name__ == "__main__":
    tester = SyncFailureTest()
    tester.test_network_interruption()
    tester.test_server_timeout()
    tester.test_auth_expiry()
    tester.test_disk_space()
    tester.generate_report()
```

### Sync Performance Benchmarking

```bash
#!/bin/bash
# sync_performance_benchmark.sh - Comprehensive sync performance testing

echo "CIDX Sync Performance Benchmark Suite"
echo "======================================"

# Configuration
REPOS=(
    "/tmp/small-repo:100:Small Repository (100 files)"
    "/tmp/medium-repo:1000:Medium Repository (1K files)"
    "/tmp/large-repo:10000:Large Repository (10K files)"
    "/tmp/huge-repo:50000:Huge Repository (50K files)"
)

# Create test repositories
create_test_repo() {
    local path=$1
    local file_count=$2
    local description=$3

    echo "Creating $description..."
    mkdir -p "$path"
    cd "$path"
    git init

    for ((i=1; i<=file_count; i++)); do
        mkdir -p "src/module_$((i/100))"
        echo "def function_$i(): return $i" > "src/module_$((i/100))/file_$i.py"
    done

    git add .
    git commit -m "Initial commit with $file_count files"
    git remote add origin "https://github.com/test/$(basename $path).git"
}

# Benchmark sync operation
benchmark_sync() {
    local path=$1
    local description=$2
    local sync_type=$3

    cd "$path"

    # Measure sync performance
    echo -e "\nBenchmarking $sync_type sync for $description"
    echo "----------------------------------------"

    # CPU and memory monitoring
    pidstat 1 > /tmp/pidstat.log 2>&1 &
    PIDSTAT_PID=$!

    # Run sync with timing
    /usr/bin/time -v cidx sync $4 2>&1 | tee /tmp/sync_benchmark.log

    # Stop monitoring
    kill $PIDSTAT_PID 2>/dev/null

    # Extract metrics
    duration=$(grep "Elapsed" /tmp/sync_benchmark.log | awk '{print $8}')
    max_memory=$(grep "Maximum resident" /tmp/sync_benchmark.log | awk '{print $6}')
    cpu_percent=$(grep "Percent of CPU" /tmp/sync_benchmark.log | awk '{print $7}')

    echo "Duration: $duration"
    echo "Max Memory: ${max_memory}KB"
    echo "CPU Usage: $cpu_percent"

    # Network usage (if applicable)
    if [ "$sync_type" == "Remote" ]; then
        bytes_sent=$(grep "bytes sent" /tmp/sync_benchmark.log | awk '{print $3}')
        bytes_received=$(grep "bytes received" /tmp/sync_benchmark.log | awk '{print $3}')
        echo "Network Sent: $bytes_sent bytes"
        echo "Network Received: $bytes_received bytes"
    fi
}

# Setup repositories
for repo_config in "${REPOS[@]}"; do
    IFS=':' read -r path file_count description <<< "$repo_config"
    create_test_repo "$path" "$file_count" "$description"
done

# Run benchmarks
echo -e "\n======================================"
echo "Starting Performance Benchmarks"
echo "======================================"

for repo_config in "${REPOS[@]}"; do
    IFS=':' read -r path file_count description <<< "$repo_config"

    # Test incremental sync
    benchmark_sync "$path" "$description" "Incremental" ""

    # Test full sync
    benchmark_sync "$path" "$description" "Full" "--full"
done

# Generate summary report
echo -e "\n======================================"
echo "Performance Benchmark Summary"
echo "======================================"
echo "See /tmp/sync_benchmark_summary.csv for detailed results"
```

---

*This comprehensive manual testing epic ensures thorough validation of both the Remote Repository Linking Mode and CIDX Repository Sync Enhancement features before production deployment. The expanded test suite includes 384 test scenarios covering all aspects of remote operation and repository synchronization. Each test scenario should be executed systematically with results documented for audit and improvement purposes.*
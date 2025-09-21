# 🧪 CIDX Client-Server Functionality Gap Closure Epic - Comprehensive Manual Testing Plan

## 📋 Executive Summary

This manual testing plan validates the complete implementation of 30 core CLI commands across 6 features that provide comprehensive CLI access to all CIDX server endpoints. The epic successfully bridges the gap between server API functionality and CLI user experience, ensuring every server capability is accessible through intuitive command-line interfaces.

**IMPLEMENTATION VERIFICATION NOTES**:
- **Actual Command Count**: 30 verified CLI commands (not 42 as originally estimated)
- **Missing Commands**: `cidx jobs history` and `cidx jobs cleanup` do not exist in implementation
- **Mode Restrictions**: `cidx repos discover` requires remote mode, not available in local mode testing
- **Authentication Commands**: All auth commands including `cidx auth reset-password` are implemented and available

## 🎯 Testing Objectives

1. **Validate Complete CLI Coverage**: Ensure all 30 verified commands work correctly with real server endpoints
2. **Test Authentication Integration**: Verify seamless login, logout, and credential management workflows
3. **Validate Repository Operations**: Test complete repository lifecycle from discovery to synchronization
4. **Test Administrative Functions**: Verify all user management and golden repository administration
5. **Test Job Monitoring**: Validate background job control and monitoring capabilities
6. **Test System Health**: Ensure comprehensive health monitoring and diagnostics
7. **Verify Integration Workflows**: Test cross-feature workflows and real-world usage patterns
8. **Performance Validation**: Ensure CLI commands respond within acceptable timeframes

## 🏗️ Test Environment Setup

### Prerequisites

#### System Requirements
- **Operating System**: Linux/macOS with Docker/Podman support
- **Git**: Version 2.0 or higher
- **Python**: Version 3.9+ with pip
- **CIDX**: Latest version installed from source
- **Network**: Stable internet connection for GitHub repository access
- **Storage**: Minimum 10GB free space for test repositories

#### Software Installation
```bash
# Install CIDX from source (current development version)
cd /home/jsbattig/Dev/code-indexer
pip install -e ".[dev]" --break-system-packages

# Verify installation
cidx --version

# Create testing directory structure
mkdir -p ~/cidx-testing/{server,projects,repos}
cd ~/cidx-testing
```

### Server Infrastructure Setup

#### - [ ] TC001: CIDX Server Installation and Startup
**Type**: Positive
**Dependencies**: None

**Given** Fresh system with CIDX source code available
**When** Installing and starting CIDX server
**Then** Server runs successfully on designated port with health endpoints accessible

**Detailed Steps**:
- [ ] Step 1: Install CIDX server infrastructure
  - **Command**: `cidx install-server --port 8090`
  - **Expected**: Server installed successfully with admin credentials created
  - **Evidence**: Installation output, ~/.cidx-server directory created
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Start the CIDX server
  - **Command**: `cd ~/.cidx-server && ./start-server.sh`
  - **Expected**: Server starts and binds to port 8090
  - **Evidence**: Server startup logs, process running
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Verify server health via curl
  - **Command**: `curl -X POST http://localhost:8090/auth/login -H "Content-Type: application/json" -d '{"username": "admin", "password": "admin"}' | jq -r '.access_token' > /tmp/admin_token.txt && curl -H "Authorization: Bearer $(cat /tmp/admin_token.txt)" http://localhost:8090/health`
  - **Expected**: Health check returns detailed status with all services healthy
  - **Evidence**: JSON response with service statuses
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Any observations about server startup performance or issues]

#### - [ ] TC002: Test Repository Preparation
**Type**: Positive
**Dependencies**: TC001

**Given** CIDX server running successfully
**When** Creating test repositories with realistic content
**Then** Test repositories available for golden repository registration

**Detailed Steps**:
- [ ] Step 1: Create primary test repository (jsbattig/tries)
  - **Command**: `cd ~/cidx-testing/repos && git clone https://github.com/jsbattig/tries.git tries-repo`
  - **Expected**: Repository cloned with multiple Pascal files and branches
  - **Evidence**: Repository directory structure, git log shows commits
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Create secondary test repository (small Python learning project)
  - **Command**: `cd ~/cidx-testing/repos && git clone https://github.com/trekhleb/learn-python.git learn-python-repo`
  - **Expected**: Small Python repository with <100 files, learning examples and test structure
  - **Evidence**: Repository files present (14 files total), Python examples organized by topic
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Verify repository branch structure
  - **Command**: `cd ~/cidx-testing/repos/tries-repo && git branch -a`
  - **Expected**: Multiple branches visible (main, potentially others)
  - **Evidence**: Branch listing output
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Repository content assessment and branch availability]

---

## 🔐 Feature 1: Enhanced Authentication Management (Stories 1-3)

### - [ ] TC003: Basic Authentication Commands
**Type**: Positive
**Dependencies**: TC001, TC002

**Given** CIDX server running with default admin credentials
**When** Testing basic authentication commands
**Then** All authentication operations work correctly with proper credential management

**Detailed Steps**:
- [ ] Step 1: Test login command with valid credentials
  - **Command**: `cidx auth login --username admin --password admin --server http://localhost:8090`
  - **Expected**: Login successful, credentials stored securely
  - **Evidence**: Success message, ~/.cidx/credentials file created
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Test authentication status
  - **Command**: `cidx auth status`
  - **Expected**: Shows logged in status with username and server details
  - **Evidence**: Status output showing current authentication state
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Test login with invalid credentials
  - **Command**: `cidx auth login --username admin --password wrongpass --server http://localhost:8090`
  - **Expected**: Login fails with clear error message
  - **Evidence**: Authentication failure message
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Test logout command
  - **Command**: `cidx auth logout`
  - **Expected**: Successfully logged out, credentials cleared
  - **Evidence**: Logout confirmation, credentials file removed
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Authentication flow observations and credential storage behavior]

### - [ ] TC004: User Registration and Password Management
**Type**: Positive
**Dependencies**: TC003

**Given** Admin user logged in successfully
**When** Testing user registration and password operations
**Then** User accounts can be created and passwords managed through CLI

**Detailed Steps**:
- [ ] Step 1: Re-authenticate as admin for user management
  - **Command**: `cidx auth login --username admin --password admin --server http://localhost:8090`
  - **Expected**: Admin authentication successful
  - **Evidence**: Login confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Register new user via CLI (Note: Using admin commands as user registration may not be directly available)
  - **Command**: `cidx admin users create testuser --password Test123!@# --email test@example.com --role normal_user`
  - **Expected**: New user created successfully
  - **Evidence**: User creation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Test password change for admin user
  - **Command**: `cidx auth change-password --old-password admin --new-password NewAdmin123!`
  - **Expected**: Password changed successfully
  - **Evidence**: Password change confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Test login with new password
  - **Command**: `cidx auth logout && cidx auth login --username admin --password NewAdmin123! --server http://localhost:8090`
  - **Expected**: Login successful with new password
  - **Evidence**: Authentication success
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Reset password back to original for remaining tests
  - **Command**: `cidx auth change-password --old-password NewAdmin123! --new-password admin`
  - **Expected**: Password reset to original value
  - **Evidence**: Password change confirmation
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [User management workflow observations]

### - [ ] TC005: Authentication Token Management and Command Verification
**Type**: Positive
**Dependencies**: TC004

**Given** User authenticated with password changes tested
**When** Testing token refresh, authentication status operations, and verifying missing command handling
**Then** Token management works correctly with proper status reporting and missing commands are handled appropriately

**Detailed Steps**:
- [ ] Step 1: Check current authentication status in detail
  - **Command**: `cidx auth status`
  - **Expected**: Detailed status showing username, server, token expiration
  - **Evidence**: Comprehensive status output
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Test token refresh functionality
  - **Command**: `cidx auth refresh`
  - **Expected**: Token refreshed successfully or informative message about refresh capabilities
  - **Evidence**: Refresh operation result
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Test authentication validation functionality
  - **Command**: `cidx auth validate`
  - **Expected**: Current credentials validated successfully
  - **Evidence**: Validation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Test password reset functionality (VERIFIED: exists in implementation)
  - **Command**: `cidx auth reset-password --username admin`
  - **Expected**: Password reset process initiated successfully
  - **Evidence**: Reset confirmation or reset process started
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Verify auth status reflects all operations accurately
  - **Command**: `cidx auth status --verbose`
  - **Expected**: Status reflects current authentication state with verbose details
  - **Evidence**: Updated comprehensive status information
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Token management behavior, command verification, and status reporting accuracy]

---

## 📦 Feature 2: User Repository Management (Stories 4-7)

### - [ ] TC006: Repository Discovery and Listing
**Type**: Positive
**Dependencies**: TC005

**Given** Admin user authenticated and test repositories prepared
**When** Testing repository discovery and listing commands
**Then** CLI provides complete repository visibility and management

**Detailed Steps**:
- [ ] Step 1: Set up golden repositories for testing (Admin operation)
  - **Command**: `curl -X POST http://localhost:8090/api/admin/golden-repos -H "Authorization: Bearer $(cat /tmp/admin_token.txt)" -H "Content-Type: application/json" -d '{"alias": "tries-golden", "git_url": "file:///home/jsbattig/cidx-testing/repos/tries-repo", "branch": "main", "description": "Pascal trie data structures"}' | jq`
  - **Expected**: Golden repository registration job created
  - **Evidence**: Job ID returned, async processing started
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Wait for repository indexing to complete and validate indexing quality
  - **Command**: `sleep 30 && curl -H "Authorization: Bearer $(cat /tmp/admin_token.txt)" http://localhost:8090/api/admin/golden-repos | jq`
  - **Expected**: Repository appears in golden repository list with indexed status
  - **Evidence**: Repository listed with metadata, indexing completion confirmed
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2a: Verify repository indexing completeness
  - **Command**: `curl -H "Authorization: Bearer $(cat /tmp/admin_token.txt)" http://localhost:8090/api/admin/golden-repos/tries-golden | jq '.indexing_status'`
  - **Expected**: Indexing status shows "completed" with file count and embedding information
  - **Evidence**: Indexing metadata shows completed status with indexed file count
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: List available repositories via CLI
  - **Command**: `cidx repos available`
  - **Expected**: Shows available golden repositories for activation
  - **Evidence**: Repository list with descriptions
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: List currently activated repositories (should be empty initially)
  - **Command**: `cidx repos list`
  - **Expected**: Empty list or "No repositories activated" message
  - **Evidence**: Empty repository listing
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Repository discovery and listing functionality]

### - [ ] TC007: Repository Activation and Lifecycle
**Type**: Positive
**Dependencies**: TC006

**Given** Golden repositories available for activation
**When** Testing repository activation and lifecycle management
**Then** Users can activate, manage, and deactivate repositories through CLI

**Detailed Steps**:
- [ ] Step 1: Activate a repository with custom alias
  - **Command**: `cidx repos activate tries-golden --alias my-tries --branch main`
  - **Expected**: Repository activation job started successfully
  - **Evidence**: Job ID returned, activation in progress
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Monitor activation progress and completion
  - **Command**: `sleep 20 && cidx repos list`
  - **Expected**: Repository appears in activated list
  - **Evidence**: Repository listed with activation details
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Get detailed repository information
  - **Command**: `cidx repos info my-tries`
  - **Expected**: Detailed repository information including branches, file count, status
  - **Evidence**: Comprehensive repository metadata
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3a: Validate semantic search functionality on activated repository
  - **Command**: `cidx query "data structure trie" --limit 5`
  - **Expected**: Semantic search returns relevant trie-related code from activated repository
  - **Evidence**: Search results with similarity scores >0.5, Pascal trie implementation code
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3b: Test semantic search quality and accuracy
  - **Command**: `cidx query "tree traversal algorithm" --min-score 0.7 --language pascal`
  - **Expected**: High-quality search results for tree traversal patterns in Pascal code
  - **Evidence**: Relevant code matches with high similarity scores, Pascal language filtering working
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Test repository deactivation
  - **Command**: `cidx repos deactivate my-tries`
  - **Expected**: Repository deactivated successfully
  - **Evidence**: Deactivation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Verify repository removed from active list
  - **Command**: `cidx repos list`
  - **Expected**: Repository no longer in activated list
  - **Evidence**: Empty or updated repository list
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Repository lifecycle management observations]

### - [ ] TC008: Repository Information and Branch Operations
**Type**: Positive
**Dependencies**: TC007

**Given** Repository lifecycle operations tested
**When** Testing branch switching and repository information commands
**Then** Users can switch branches and get detailed repository information

**Detailed Steps**:
- [ ] Step 1: Re-activate repository for branch testing
  - **Command**: `cidx repos activate tries-golden --alias tries-branch-test --branch main`
  - **Expected**: Repository activated successfully
  - **Evidence**: Activation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Get repository information with branch details
  - **Command**: `cidx repos info tries-branch-test`
  - **Expected**: Repository info shows current branch as main
  - **Evidence**: Branch information in repository details
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Test branch switching (if multiple branches available)
  - **Command**: `cidx repos switch-branch tries-branch-test --branch master`
  - **Expected**: Branch switched successfully or clear message about available branches
  - **Evidence**: Branch switch confirmation or branch availability info
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Verify branch switch reflected in repository info
  - **Command**: `cidx repos info tries-branch-test`
  - **Expected**: Repository info shows updated branch
  - **Evidence**: Updated branch information
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Test repository synchronization
  - **Command**: `cidx repos sync tries-branch-test`
  - **Expected**: Repository synchronized with golden repository
  - **Evidence**: Sync operation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Branch operations and repository information accuracy]

---

## ⚙️ Feature 3: Job Monitoring and Control (Stories 8-9)

### - [ ] TC009: Job Listing and Monitoring
**Type**: Positive
**Dependencies**: TC008

**Given** Repository operations completed with background jobs
**When** Testing job monitoring and listing commands
**Then** Users can monitor and control background job execution

**Detailed Steps**:
- [ ] Step 1: List all user jobs
  - **Command**: `cidx jobs list`
  - **Expected**: Shows recent repository activation and operation jobs
  - **Evidence**: Job list with operation types and statuses
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Get detailed status of a specific job
  - **Command**: `cidx jobs list | head -n 1 | grep -o 'job_[a-zA-Z0-9]*' | head -n 1 > /tmp/job_id.txt && cidx jobs status $(cat /tmp/job_id.txt)`
  - **Expected**: Detailed job information including progress and results
  - **Evidence**: Comprehensive job status details
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Start a long-running operation to test job monitoring
  - **Command**: `cidx repos activate tries-golden --alias job-test-repo --branch main`
  - **Expected**: Job started and job ID returned
  - **Evidence**: Job creation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Monitor job progress in real-time
  - **Command**: `cidx jobs list | grep activate | tail -n 1 | grep -o 'job_[a-zA-Z0-9]*' > /tmp/new_job_id.txt && cidx jobs status $(cat /tmp/new_job_id.txt)`
  - **Expected**: Job status shows progress information
  - **Evidence**: Job progress and status details
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Job monitoring capabilities and information detail]

### - [ ] TC010: Job Control and Cancellation
**Type**: Positive/Edge Case
**Dependencies**: TC009

**Given** Jobs running in background
**When** Testing job cancellation and control commands
**Then** Users can cancel jobs and manage job execution

**Detailed Steps**:
- [ ] Step 1: Start a cancellable operation
  - **Command**: `cidx repos activate tries-golden --alias cancel-test --branch main`
  - **Expected**: Job started successfully
  - **Evidence**: Job ID returned
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Quickly attempt to cancel the job
  - **Command**: `cidx jobs list | grep activate | tail -n 1 | grep -o 'job_[a-zA-Z0-9]*' > /tmp/cancel_job_id.txt && cidx jobs cancel $(cat /tmp/cancel_job_id.txt)`
  - **Expected**: Job cancellation attempted or completion notice if job finished quickly
  - **Evidence**: Cancellation result or job completion notification
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Verify job status after cancellation attempt
  - **Command**: `cidx jobs status $(cat /tmp/cancel_job_id.txt)`
  - **Expected**: Job shows cancelled status or completed status with clear indication
  - **Evidence**: Final job status
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Test job listing with various filters
  - **Command**: `cidx jobs list --status completed && cidx jobs list --status failed`
  - **Expected**: Jobs filtered by status correctly
  - **Evidence**: Filtered job lists
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Job control effectiveness and status management]

---

## 👥 Feature 4: Administrative User Management (Stories 10-12)

### - [ ] TC011: Administrative User Creation and Management
**Type**: Positive
**Dependencies**: TC010

**Given** Admin user authenticated and system operational
**When** Testing administrative user management commands
**Then** Admin can create, manage, and delete users through CLI

**Detailed Steps**:
- [ ] Step 1: Create a new normal user
  - **Command**: `cidx admin users create normaluser --password NormalPass123! --email normal@example.com --role normal_user`
  - **Expected**: User created successfully
  - **Evidence**: User creation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Create a power user
  - **Command**: `cidx admin users create poweruser --password PowerPass123! --email power@example.com --role power_user`
  - **Expected**: Power user created successfully
  - **Evidence**: User creation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: List all users in the system
  - **Command**: `cidx admin users list`
  - **Expected**: Shows all users with roles and details
  - **Evidence**: Complete user listing
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Show detailed information for a specific user
  - **Command**: `cidx admin users show normaluser`
  - **Expected**: Detailed user information including role and status
  - **Evidence**: Comprehensive user details
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [User creation and management functionality]

### - [ ] TC012: User Role Management and Updates
**Type**: Positive
**Dependencies**: TC011

**Given** Multiple users created with different roles
**When** Testing user role updates and management
**Then** Admin can update user roles and properties

**Detailed Steps**:
- [ ] Step 1: Update user role from normal_user to power_user
  - **Command**: `cidx admin users update normaluser --role power_user`
  - **Expected**: User role updated successfully
  - **Evidence**: Role update confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Verify role change reflected in user listing
  - **Command**: `cidx admin users show normaluser`
  - **Expected**: User now shows power_user role
  - **Evidence**: Updated user details
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Change user password as admin
  - **Command**: `cidx admin users change-password normaluser --new-password NewNormalPass123!`
  - **Expected**: Password changed successfully
  - **Evidence**: Password change confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Verify password change by testing login
  - **Command**: `cidx auth logout && cidx auth login --username normaluser --password NewNormalPass123! --server http://localhost:8090`
  - **Expected**: Login successful with new password
  - **Evidence**: Authentication success
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Log back in as admin for remaining tests
  - **Command**: `cidx auth logout && cidx auth login --username admin --password admin --server http://localhost:8090`
  - **Expected**: Admin authentication restored
  - **Evidence**: Admin login confirmation
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Role management and password administration]

### - [ ] TC013: User Deletion and Security
**Type**: Positive/Edge Case
**Dependencies**: TC012

**Given** Multiple users exist in the system
**When** Testing user deletion and security constraints
**Then** Admin can delete users with appropriate safety measures

**Detailed Steps**:
- [ ] Step 1: Attempt to delete a regular user
  - **Command**: `cidx admin users delete poweruser`
  - **Expected**: User deleted successfully
  - **Evidence**: Deletion confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Verify user removed from system
  - **Command**: `cidx admin users list`
  - **Expected**: Deleted user no longer appears in list
  - **Evidence**: Updated user list without deleted user
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Test deletion of non-existent user
  - **Command**: `cidx admin users delete nonexistentuser`
  - **Expected**: Clear error message about user not found
  - **Evidence**: User not found error
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Attempt to delete last admin user (should be protected)
  - **Command**: `cidx admin users delete admin`
  - **Expected**: Deletion prevented with security message
  - **Evidence**: Security protection message
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [User deletion safety and security constraints]

---

## 🗂️ Feature 5: Golden Repository Administration (Stories 13-15)

### - [ ] TC014: Golden Repository Addition and Management
**Type**: Positive
**Dependencies**: TC013

**Given** Admin user with golden repository management access
**When** Testing golden repository addition and management
**Then** Admin can add, list, and manage golden repositories

**Detailed Steps**:
- [ ] Step 1: Add a new golden repository from GitHub
  - **Command**: `cidx admin repos add hello-world --url https://github.com/octocat/Hello-World.git --branch main --description "GitHub Hello World example repository"`
  - **Expected**: Repository addition job started successfully
  - **Evidence**: Job ID returned for repository processing
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Monitor repository addition progress
  - **Command**: `sleep 30 && cidx admin repos list`
  - **Expected**: New repository appears in golden repository list
  - **Evidence**: Repository listed with metadata
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Show detailed information for the new repository
  - **Command**: `cidx admin repos show hello-world`
  - **Expected**: Detailed repository information including branches and status
  - **Evidence**: Comprehensive repository details
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Add a local repository
  - **Command**: `cidx admin repos add local-test --url file:///home/jsbattig/cidx-testing/repos/hello-world-repo --branch main --description "Local test repository"`
  - **Expected**: Local repository added successfully
  - **Evidence**: Repository addition confirmation
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Golden repository addition and management capabilities]

### - [ ] TC015: Golden Repository Refresh and Maintenance
**Type**: Positive
**Dependencies**: TC014

**Given** Golden repositories exist in the system
**When** Testing repository refresh and maintenance operations
**Then** Admin can refresh and maintain golden repositories

**Detailed Steps**:
- [ ] Step 1: Refresh an existing golden repository
  - **Command**: `cidx admin repos refresh tries-golden`
  - **Expected**: Repository refresh job started successfully
  - **Evidence**: Refresh job ID returned
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Monitor refresh progress
  - **Command**: `sleep 20 && cidx admin repos show tries-golden`
  - **Expected**: Repository shows updated information or refresh completion
  - **Evidence**: Updated repository metadata
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: List all golden repositories with status
  - **Command**: `cidx admin repos list`
  - **Expected**: All repositories listed with current status and metadata
  - **Evidence**: Complete repository listing
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Refresh a repository that may not need updates
  - **Command**: `cidx admin repos refresh hello-world`
  - **Expected**: Refresh completed successfully even if no changes
  - **Evidence**: Refresh operation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Repository refresh and maintenance functionality]

### - [ ] TC016: Golden Repository Deletion and Cleanup
**Type**: Positive/Edge Case
**Dependencies**: TC015

**Given** Multiple golden repositories available
**When** Testing repository deletion and cleanup operations
**Then** Admin can delete repositories with proper cleanup

**Detailed Steps**:
- [ ] Step 1: Delete a golden repository
  - **Command**: `cidx admin repos delete local-test`
  - **Expected**: Repository deletion job started or completed successfully
  - **Evidence**: Deletion confirmation or job ID
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Verify repository removed from listing
  - **Command**: `cidx admin repos list`
  - **Expected**: Deleted repository no longer appears in list
  - **Evidence**: Updated repository list
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Attempt to delete non-existent repository
  - **Command**: `cidx admin repos delete nonexistent-repo`
  - **Expected**: Clear error message about repository not found
  - **Evidence**: Repository not found error
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Test deletion of repository with active users (if applicable)
  - **Command**: `cidx admin repos delete hello-world`
  - **Expected**: Deletion proceeds or clear message about active usage
  - **Evidence**: Deletion result or usage warning
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Repository deletion and cleanup effectiveness]

---

## 🏥 Feature 6: System Health Monitoring (Stories 16-17)

### - [ ] TC017: Basic System Health Monitoring
**Type**: Positive
**Dependencies**: TC016

**Given** CIDX system fully operational with repositories and users
**When** Testing system health monitoring commands
**Then** CLI provides comprehensive system health information

**Detailed Steps**:
- [ ] Step 1: Check basic system health
  - **Command**: `cidx system health`
  - **Expected**: Overall system health status with basic service information
  - **Evidence**: Health summary with service statuses
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Check detailed system health
  - **Command**: `cidx system health --detailed`
  - **Expected**: Detailed health information including service metrics
  - **Evidence**: Comprehensive health report with metrics
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Check verbose system health
  - **Command**: `cidx system health --verbose`
  - **Expected**: Very detailed health information including performance data
  - **Evidence**: Extensive health report with performance metrics
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Monitor health during active operations
  - **Command**: `cidx repos activate tries-golden --alias health-test & sleep 5 && cidx system health --detailed`
  - **Expected**: Health check shows system handling active operations properly
  - **Evidence**: Health status during load
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [System health monitoring completeness and accuracy]

### - [ ] TC018: Health Monitoring Under Load
**Type**: Performance
**Dependencies**: TC017

**Given** System health monitoring commands working
**When** Testing health monitoring under various system loads
**Then** Health monitoring provides accurate information under all conditions

**Detailed Steps**:
- [ ] Step 1: Baseline health check with idle system
  - **Command**: `cidx system health --verbose`
  - **Expected**: All services healthy with good performance metrics
  - **Evidence**: Baseline health metrics
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Health check during repository operations
  - **Command**: `cidx admin repos refresh tries-golden & sleep 2 && cidx system health --detailed`
  - **Expected**: Health check shows active operations without degradation
  - **Evidence**: Health status during repository operations
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Health check with multiple concurrent operations
  - **Command**: `cidx repos activate tries-golden --alias load-test-1 & cidx admin repos refresh hello-world & sleep 3 && cidx system health --verbose`
  - **Expected**: System remains healthy during concurrent operations
  - **Evidence**: Health status under load
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Verify health monitoring responsiveness
  - **Command**: `time cidx system health --detailed`
  - **Expected**: Health check completes quickly (under 5 seconds)
  - **Evidence**: Response time measurement
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Health monitoring performance and accuracy under load]

---

## 🔄 Integration Workflows and Cross-Feature Testing

### - [ ] TC019: Complete Administrator Workflow
**Type**: Integration
**Dependencies**: TC018

**Given** All individual features tested successfully
**When** Testing complete administrator workflow end-to-end
**Then** Admin can perform complete repository and user management workflow

**Detailed Steps**:
- [ ] Step 1: Create complete user management scenario
  - **Command**: `cidx admin users create testadmin --password TestAdmin123! --email testadmin@example.com --role admin`
  - **Expected**: New admin user created successfully
  - **Evidence**: Admin user creation confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Switch to new admin and perform repository management
  - **Command**: `cidx auth logout && cidx auth login --username testadmin --password TestAdmin123! --server http://localhost:8090`
  - **Expected**: New admin can authenticate and access admin functions
  - **Evidence**: Authentication success with admin privileges
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Add repository as new admin
  - **Command**: `cidx admin repos add workflow-test --url https://github.com/octocat/Hello-World.git --branch main --description "Workflow test repository"`
  - **Expected**: New admin can add golden repositories
  - **Evidence**: Repository addition success
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Create and manage users as new admin
  - **Command**: `cidx admin users create workflowuser --password WorkflowPass123! --email workflow@example.com --role power_user`
  - **Expected**: New admin can create users
  - **Evidence**: User creation success
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Monitor system health as admin
  - **Command**: `cidx system health --detailed`
  - **Expected**: Admin can access system health information
  - **Evidence**: Health information available
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Complete administrator workflow effectiveness]

### - [ ] TC020: Complete User Workflow (Repository Operations)
**Type**: Integration
**Dependencies**: TC019

**Given** Admin workflow completed and users created
**When** Testing complete user repository workflow
**Then** Users can perform complete repository lifecycle operations

**Detailed Steps**:
- [ ] Step 1: Switch to power user account
  - **Command**: `cidx auth logout && cidx auth login --username workflowuser --password WorkflowPass123! --server http://localhost:8090`
  - **Expected**: Power user authentication successful
  - **Evidence**: User authentication confirmation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Discover and activate repositories as user
  - **Command**: `cidx repos available && cidx repos activate tries-golden --alias user-workflow-repo --branch main`
  - **Expected**: User can see available repositories and activate them
  - **Evidence**: Repository discovery and activation success
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Perform repository operations
  - **Command**: `cidx repos info user-workflow-repo && cidx repos sync user-workflow-repo`
  - **Expected**: User can get repository information and sync repositories
  - **Evidence**: Repository information and sync success
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Monitor jobs as user
  - **Command**: `cidx jobs list && cidx system health`
  - **Expected**: User can monitor their jobs and basic system health
  - **Evidence**: Job listing and health information
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Test user permission boundaries
  - **Command**: `cidx admin users list`
  - **Expected**: Command fails with permission error
  - **Evidence**: Permission denied error message
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Complete user workflow and permission enforcement]

### - [ ] TC021: Error Handling and Edge Cases
**Type**: Edge Case
**Dependencies**: TC020

**Given** All workflows tested successfully
**When** Testing error conditions and edge cases
**Then** CLI handles errors gracefully with informative messages

**Detailed Steps**:
- [ ] Step 1: Test authentication with expired/invalid credentials
  - **Command**: `cidx auth logout && cidx auth login --username invaliduser --password wrongpass --server http://localhost:8090`
  - **Expected**: Clear authentication failure message
  - **Evidence**: Informative error message
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Test operations without authentication
  - **Command**: `cidx repos list`
  - **Expected**: Clear message about authentication requirement
  - **Evidence**: Authentication required error
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Test invalid repository operations
  - **Command**: `cidx auth login --username admin --password admin --server http://localhost:8090 && cidx repos activate nonexistent-repo --alias test`
  - **Expected**: Clear error about repository not found
  - **Evidence**: Repository not found error
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Test malformed commands
  - **Command**: `cidx admin users create && cidx repos activate`
  - **Expected**: Clear usage messages for incomplete commands
  - **Evidence**: Usage help and error messages
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Test server connectivity issues
  - **Command**: `cidx auth logout && cidx auth login --username admin --password admin --server http://localhost:8091`
  - **Expected**: Clear connection error message
  - **Evidence**: Server connection error
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Error handling quality and user guidance]

### - [ ] TC022: Performance and Response Time Validation
**Type**: Performance
**Dependencies**: TC021

**Given** All functionality verified and error handling tested
**When** Testing CLI command performance and response times
**Then** All CLI commands respond within acceptable timeframes

**Detailed Steps**:
- [ ] Step 1: Measure authentication performance
  - **Command**: `cidx auth logout && time cidx auth login --username admin --password admin --server http://localhost:8090`
  - **Expected**: Authentication completes within 30 seconds (per conversation: >30 seconds = WAY too long)
  - **Evidence**: Timing measurement output
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Measure repository listing performance
  - **Command**: `time cidx repos available && time cidx repos list`
  - **Expected**: Repository listings complete within 30 seconds each (per conversation: >30 seconds = WAY too long)
  - **Evidence**: Timing measurements
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Measure admin operations performance
  - **Command**: `time cidx admin users list && time cidx admin repos list`
  - **Expected**: Admin listings complete within 30 seconds each (per conversation: >30 seconds = WAY too long)
  - **Evidence**: Performance measurements
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Measure health check performance
  - **Command**: `time cidx system health --detailed`
  - **Expected**: Health check completes within 30 seconds (per conversation: >30 seconds = WAY too long)
  - **Evidence**: Health check timing
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Measure job operations performance
  - **Command**: `time cidx jobs list`
  - **Expected**: Job listing completes within 30 seconds (per conversation: >30 seconds = WAY too long)
  - **Evidence**: Job operation timing
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Performance characteristics and response time acceptability]

### - [ ] TC023: Concurrent User Operations and Resource Contention
**Type**: Performance/Edge Case
**Dependencies**: TC022

**Given** System performing well under single user load
**When** Testing concurrent user operations and resource contention scenarios
**Then** System handles multiple users gracefully without conflicts or performance degradation

**Detailed Steps**:
- [ ] Step 1: Set up multiple user sessions concurrently
  - **Command**: `cidx auth login --username admin --password admin --server http://localhost:8090 & cidx auth login --username workflowuser --password WorkflowPass123! --server http://localhost:8090 & wait`
  - **Expected**: Both users can authenticate simultaneously without conflicts
  - **Evidence**: Both authentication sessions successful, no credential conflicts
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 2: Test concurrent repository activation by different users
  - **Command**: `cidx repos activate tries-golden --alias admin-concurrent-repo --branch main & cidx repos activate tries-golden --alias user-concurrent-repo --branch main & wait`
  - **Expected**: Both users can activate same golden repository concurrently with different aliases
  - **Evidence**: Both activation jobs succeed, no resource conflicts
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 3: Test concurrent semantic searches on same repository
  - **Command**: `cidx query "data structure" --limit 3 & cidx query "algorithm implementation" --limit 3 & wait`
  - **Expected**: Concurrent semantic searches complete successfully without interference
  - **Evidence**: Both queries return results, no query conflicts or timeouts
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 4: Test concurrent admin operations
  - **Command**: `cidx admin users list & cidx admin repos list & cidx system health --detailed & wait`
  - **Expected**: Concurrent admin operations complete without resource contention
  - **Evidence**: All operations complete successfully, no performance degradation
  - **Result**: [✓ Pass / ✗ Fail]

- [ ] Step 5: Monitor system health during concurrent operations
  - **Command**: `cidx repos sync admin-concurrent-repo & cidx repos sync user-concurrent-repo & sleep 3 && cidx system health --detailed`
  - **Expected**: System maintains healthy status during concurrent operations
  - **Evidence**: Health check shows normal operation, no resource exhaustion
  - **Result**: [✓ Pass / ✗ Fail]

**Overall Test Result**: [✓ Pass / ✗ Fail]
**Notes**: [Concurrent user handling effectiveness and resource management]

---

## 📋 Test Execution Summary Template

### Overall Testing Results

**Test Execution Date**: _____________________
**Tester**: _____________________
**CIDX Version**: _____________________
**Test Environment**: _____________________

### Feature Coverage Results

| Feature | Test Cases | Passed | Failed | Success Rate | Notes |
|---------|------------|--------|--------|--------------|-------|
| **Feature 1: Enhanced Authentication Management** | 3 | __ | __ | __% | _____________ |
| **Feature 2: User Repository Management** | 3 | __ | __ | __% | _____________ |
| **Feature 3: Job Monitoring and Control** | 2 | __ | __ | __% | _____________ |
| **Feature 4: Administrative User Management** | 3 | __ | __ | __% | _____________ |
| **Feature 5: Golden Repository Administration** | 3 | __ | __ | __% | _____________ |
| **Feature 6: System Health Monitoring** | 2 | __ | __ | __% | _____________ |
| **Integration Workflows** | 4 | __ | __ | __% | _____________ |
| **Concurrent User Testing** | 1 | __ | __ | __% | _____________ |
| **TOTALS** | **23** | __ | __ | __% | _____________ |

### CLI Commands Tested

**Feature 1 - Authentication (8 commands)**:
- [ ] `cidx auth login` - User authentication with credentials
- [ ] `cidx auth logout` - User logout and credential clearing
- [ ] `cidx auth status` - Authentication status checking
- [ ] `cidx auth change-password` - User password modification
- [ ] `cidx auth refresh` - Token refresh operations
- [ ] `cidx auth register` - New user registration
- [ ] `cidx auth reset-password` - Password reset initiation (VERIFIED: exists in implementation)
- [ ] `cidx auth update` - Update remote credentials
- [ ] `cidx auth validate` - Validate current credentials

**Feature 2 - Repository Management (9 commands)**:
- [ ] `cidx repos list` - List activated repositories
- [ ] `cidx repos available` - List available golden repositories
- [ ] `cidx repos activate` - Activate repository with alias and branch
- [ ] `cidx repos deactivate` - Deactivate user repository
- [ ] `cidx repos info` - Get detailed repository information
- [ ] `cidx repos switch-branch` - Switch repository branch
- [ ] `cidx repos sync` - Synchronize with golden repository
- [ ] `cidx repos status` - Show comprehensive repository status overview
- [ ] `cidx repos sync-status` - Show repository sync status
**NOTE**: `cidx repos discover` requires remote mode and is not testable in local mode

**Feature 3 - Job Monitoring (3 commands)**:
- [ ] `cidx jobs list` - List user jobs with status
- [ ] `cidx jobs status` - Get detailed job information
- [ ] `cidx jobs cancel` - Cancel running job
**NOTE**: `cidx jobs history` and `cidx jobs cleanup` do NOT exist in implementation

**Feature 4 - User Administration (6 commands)**:
- [ ] `cidx admin users create` - Create new user account
- [ ] `cidx admin users list` - List all system users
- [ ] `cidx admin users show` - Show detailed user information
- [ ] `cidx admin users update` - Update user role and properties
- [ ] `cidx admin users delete` - Delete user account
- [ ] `cidx admin users change-password` - Change user password as admin

**Feature 5 - Repository Administration (5 commands)**:
- [ ] `cidx admin repos add` - Add new golden repository
- [ ] `cidx admin repos list` - List all golden repositories
- [ ] `cidx admin repos show` - Show detailed repository information
- [ ] `cidx admin repos refresh` - Refresh repository content
- [ ] `cidx admin repos delete` - Delete golden repository

**Feature 6 - System Health (1 command with options)**:
- [ ] `cidx system health` - Basic system health check
- [ ] `cidx system health --detailed` - Detailed health information
- [ ] `cidx system health --verbose` - Comprehensive health diagnostics

**Total CLI Commands Validated**: **30 commands** (VERIFIED: actual implementation count, not 42)

**IMPLEMENTATION REALITY CHECK**:
- **Auth commands**: 8 verified (including reset-password, update, validate)
- **Repos commands**: 9 verified (discover requires remote mode)
- **Jobs commands**: 3 verified (history/cleanup do not exist)
- **Admin Users commands**: 6 verified
- **Admin Repos commands**: 5 verified
- **System commands**: 1 verified (with multiple option flags)
- **Total verified**: 30 actual commands available for testing

### Critical Issues Discovered

| Issue ID | Description | Severity | Feature | Status | Resolution |
|----------|-------------|----------|---------|--------|------------|
| | | | | | |
| | | | | | |
| | | | | | |

### Performance Metrics

| Operation Type | Average Response Time | Acceptable Threshold | Status |
|----------------|----------------------|---------------------|---------|
| Authentication | _____ seconds | < 30 seconds | Pass/Fail |
| Repository Listing | _____ seconds | < 30 seconds | Pass/Fail |
| Admin Operations | _____ seconds | < 30 seconds | Pass/Fail |
| Health Checks | _____ seconds | < 30 seconds | Pass/Fail |
| Job Operations | _____ seconds | < 30 seconds | Pass/Fail |

### Production Readiness Assessment

**Security**: [ ] Excellent [ ] Good [ ] Needs Improvement [ ] Fail
**Functionality**: [ ] Complete [ ] Mostly Complete [ ] Partial [ ] Incomplete
**Performance**: [ ] Excellent [ ] Good [ ] Acceptable [ ] Poor
**Error Handling**: [ ] Excellent [ ] Good [ ] Needs Improvement [ ] Poor
**User Experience**: [ ] Excellent [ ] Good [ ] Acceptable [ ] Poor

### Final Recommendation

[ ] **APPROVED FOR PRODUCTION** - All critical functionality working
[ ] **APPROVED WITH CONDITIONS** - Minor issues noted, production acceptable
[ ] **REQUIRES FIXES** - Critical issues must be resolved before production
[ ] **NOT READY** - Major functionality gaps or critical failures

### Additional Notes

**Successful Workflows**:
-
-
-

**Areas for Improvement**:
-
-
-

**Recommendations**:
-
-
-

### Tester Sign-off

**Tester Name**: _____________________
**Date**: _____________________
**Signature**: _____________________

---

## 🛠️ Troubleshooting Guide

### Common Issues and Solutions

#### Authentication Issues
- **"Invalid credentials"**: Verify server is running and credentials are correct
- **"Token expired"**: Use `cidx auth refresh` or re-login with `cidx auth login`
- **"Connection refused"**: Check server status and port configuration

#### Repository Issues
- **"Repository not found"**: Verify repository alias and check `cidx repos available`
- **"Branch not found"**: List available branches and verify branch name
- **"Activation failed"**: Check server logs and golden repository status

#### Permission Issues
- **"Admin access required"**: Ensure logged in with admin credentials
- **"Insufficient permissions"**: Verify user role matches required permissions
- **"Access denied"**: Check authentication status with `cidx auth status`

#### Performance Issues
- **Slow responses**: Check server health with `cidx system health --detailed`
- **Timeouts**: Verify network connectivity and server resource usage
- **High memory usage**: Monitor system resources during operations

### Emergency Procedures

#### Server Issues
1. Check server process: `ps aux | grep cidx`
2. Restart server: `cd ~/.cidx-server && ./start-server.sh`
3. Check logs: `tail -f ~/.cidx-server/logs/server.log`

#### Data Issues
1. Backup data: `cp -r ~/.cidx-server/data ~/.cidx-server/data.backup`
2. Check disk space: `df -h ~/.cidx-server`
3. Verify database integrity through health checks

This comprehensive manual testing plan ensures complete validation of the CIDX Client-Server Functionality Gap Closure Epic, providing thorough testing of all 42 CLI commands across 6 features with real-world usage scenarios and proper error handling validation.
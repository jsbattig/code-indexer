# Epic: Remote Mode Manual Testing Plan

## 🎯 **Epic Intent**

Create comprehensive manual testing procedures that validate 100% of CIDX remote mode functionality through systematic command-line testing, ensuring production readiness for hybrid local/remote operation with team-shared indexing capabilities.

[Conversation Reference: "Create comprehensive Epic→Features→Stories structure for manual testing of CIDX remote mode functionality with 100% capability coverage"]

## 📋 **Epic Summary**

This epic provides exhaustive manual testing coverage for CIDX remote mode functionality, validating the complete transformation from local-only to hybrid local/remote operation. The testing strategy focuses on practical, executable test procedures that can be performed by developers, QA engineers, or automated agents through actual command execution and manual verification.

[Conversation Reference: "The goal is to create executable test procedures that validate all remote mode capabilities through actual command execution"]

## 🏗️ **Testing Architecture Overview**

### Real Server Testing Environment - Code-Indexer Repository
```
CIDX Manual Testing Environment (Testing Against THIS Repository)
├── CIDX Server (localhost:8095) - REAL SERVER REQUIRED
├── Real Commands (python -m code_indexer.cli vs python -m code_indexer.cli)
├── Real Credentials (admin/admin from server setup)
├── Target Repository: /home/jsbattig/Dev/code-indexer (THIS repository)
│   ├── Main CLI: src/code_indexer/cli.py (237KB, core commands)
│   ├── Server: src/code_indexer/server/ (15 modules, auth, API endpoints)
│   ├── Remote Mode: src/code_indexer/remote/ (health checker, config, credentials)
│   ├── Authentication: server/auth/ (JWT, user management, security)
│   └── Services: services/ (file chunking, docker, git processing)
└── Expected Query Content: "authentication", "JWT", "server", "CLI", "remote mode"
```

### Command-Driven Testing Philosophy
- Each test story uses REAL working server on localhost:8095
- Tests both pipx-installed python -m code_indexer.cli and development python -m code_indexer.cli
- Validates actual implemented features (status, query, init)
- Tests real failure scenarios encountered in development
- Complete vertical testing slices from CLI to server response

[Conversation Reference: "Command-Driven Testing: Each test story specifies exact python -m code_indexer.cli commands to execute"]

## 🎯 **Business Value Validation**

### Key Testing Objectives
- **Zero Setup Time**: Validate instant remote querying without local containers
- **Team Collaboration**: Verify shared indexing across multiple users
- **Security Compliance**: Ensure encrypted credentials and JWT authentication
- **Performance Targets**: Confirm <2x query time vs local operation
- **User Experience**: Validate identical UX between local and remote modes

[Conversation Reference: "Manual testing of CIDX remote mode functionality with 100% capability coverage"]

## 🔧 **Implementation Features**

### Feature 0: Server Setup (Implementation Order: 0th - PREREQUISITE)
**Priority**: Critical - blocks ALL testing
**Stories**: 1 server environment setup story
- Real server startup and verification
- API endpoint health validation

### Feature 1: Connection Setup (Implementation Order: 1st)
**Priority**: Highest - blocks all other testing
**Stories**: 2 connection and verification stories
- Remote initialization testing
- Connection verification procedures

### Feature 2: Authentication Security (Implementation Order: 2nd)
**Priority**: High - required for secured operations
**Stories**: 2 authentication flow and security stories
- Login/logout flow testing
- Token lifecycle management validation

### Feature 3: Repository Management (Implementation Order: 3rd)
**Priority**: High - core functionality
**Stories**: 2 repository discovery and linking stories
- Repository discovery testing
- Repository linking validation

### Feature 4: Semantic Search (Implementation Order: 4th)
**Priority**: High - primary use case
**Stories**: 2 semantic query functionality stories
- Basic query testing
- Advanced query options validation

### Feature 5: Repository Synchronization (Implementation Order: 5th)
**Priority**: Medium - enhanced capability
**Stories**: 1 synchronization story
- Manual sync operations testing

### Feature 6: Error Handling (Implementation Order: 6th)
**Priority**: Medium - robustness validation
**Stories**: 2 network failure and error recovery stories
- Network error testing
- Error recovery validation

### Feature 7: Performance Validation (Implementation Order: 7th)
**Priority**: Low - optimization verification
**Stories**: 2 response time and reliability stories
- Response time testing
- Reliability validation

### Feature 8: Multi-User Scenarios (Implementation Order: 8th)
**Priority**: Low - advanced use cases
**Stories**: 2 concurrent usage stories
- Concurrent usage testing
- Multi-user validation

### Feature 9: Branch Management Operations (Implementation Order: 9th)
**Priority**: Medium - developer workflow support
**Stories**: 2 branch listing and switching stories
- Branch listing operations testing
- Branch switching functionality validation

### Feature 10: Credential Rotation System (Implementation Order: 10th)
**Priority**: Medium - security operations
**Stories**: 1 credential update story
- Basic credential update operations testing

### Feature 11: Project Data Cleanup Operations (Implementation Order: 11th)
**Priority**: Medium - development efficiency
**Stories**: 1 project cleanup story
- Single project data cleanup testing

### Feature 12: Sync Job Monitoring and Progress Tracking (Implementation Order: 12th)
**Priority**: Medium - operational visibility
**Stories**: 1 job tracking story
- Sync job submission and tracking testing

[Conversation Reference: "12 feature folders with comprehensive coverage including branch management, credential rotation, project cleanup, and sync job monitoring"]

## 🎯 **Acceptance Criteria**

### Functional Requirements
- ✅ Manual test procedures for remote mode initialization with server/username/password
- ✅ Identical query UX validation between local and remote modes
- ✅ Intelligent branch matching testing using git merge-base analysis
- ✅ File-level staleness detection with timestamp comparison testing
- ✅ JWT token refresh and re-authentication testing
- ✅ Encrypted credential storage validation

[Conversation Reference: "Clear pass/fail criteria for manual verification"]

### Non-Functional Requirements
- ✅ Zero impact on existing local mode functionality validation
- ✅ Network error resilience testing with clear user guidance
- ✅ Performance testing within 2x local query time
- ✅ Security testing with credential encryption validation

[Conversation Reference: "Real server testing with actual results validation"]

## 📊 **Success Metrics**

### User Experience Metrics
- **Command Parity**: 100% identical UX validation between local and remote query operations
- **Setup Time**: Remote mode initialization completable in <60 seconds
- **Error Clarity**: All error messages provide actionable next steps
- **Branch Matching**: >95% success rate for intelligent branch linking

### Performance Metrics
- **Query Response**: Remote queries complete within 2x local query time
- **Network Resilience**: Graceful degradation on network failures
- **Token Lifecycle**: Automatic refresh prevents authentication interruptions

[Conversation Reference: "Performance Requirements: Query responses within 2 seconds for typical operations"]

## 🚀 **Implementation Timeline**

### Phase 1: Core Connection Testing (Features 1-4)
- Connection setup, authentication, repository management, semantic search
- Core remote architecture validation
- Essential functionality verification

### Phase 2: Advanced Features Testing (Features 5-8)
- Repository synchronization, branch operations, staleness detection, error handling
- Advanced feature validation
- Robustness and reliability testing

### Phase 3: Performance & Maintenance Testing (Features 9-11)
- Performance validation, multi-user scenarios, cleanup maintenance
- Polish, optimization, and lifecycle testing

[Conversation Reference: "Clear implementation order based on dependencies"]

## 📋 **Feature Summary**

| Feature | Priority | Stories | Description |
|---------|----------|---------|-------------|
| **Feature 1** | Highest | 2 | Connection Setup |
| **Feature 2** | High | 2 | Authentication Security |
| **Feature 3** | High | 2 | Repository Management |
| **Feature 4** | High | 2 | Semantic Search |
| **Feature 5** | Medium | 1 | Repository Synchronization |
| **Feature 6** | Medium | 2 | Error Handling |
| **Feature 7** | Low | 2 | Performance Validation |
| **Feature 8** | Low | 2 | Multi-User Scenarios |

**Total Stories**: 15 across 8 features
**Testing Strategy**: Manual command execution with real server validation
**Verification Method**: Human-readable pass/fail assessment

[Conversation Reference: "Individual story files with specific commands and acceptance criteria"]

## 🏗️ **Testing Infrastructure Requirements**

### Technology Stack
- **Testing Method**: Manual command execution
- **Server Setup**: Single CIDX server instance
- **Validation**: Human-readable pass/fail assessment
- **Concurrency**: Multiple manual agents when needed

### Testing Environment
- One CIDX server (localhost or remote)
- Test repository with multiple branches
- Test user accounts with different permissions
- Manual execution environment with python -m code_indexer.cli CLI

[Conversation Reference: "Simple Manual Testing Approach: One test server, real commands, manual verification"]

## 📝 **Implementation Notes**

This manual testing epic focuses on practical, executable test procedures rather than complex infrastructure. Each feature contains stories with specific commands and clear acceptance criteria that can be executed systematically to validate remote mode functionality.

The emphasis is on:
- Real command execution over simulation
- Clear pass/fail criteria over complex metrics
- Practical validation over theoretical coverage
- Systematic testing over ad-hoc validation

[Conversation Reference: "Focus on practical, executable test procedures rather than complex infrastructure"]
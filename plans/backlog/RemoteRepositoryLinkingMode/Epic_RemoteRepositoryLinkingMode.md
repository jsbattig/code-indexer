# Epic: Remote Repository Linking Mode

## 🎯 **Epic Intent**

Transform CIDX from local-only to hybrid local/remote with shared team indexing while maintaining identical UX. Enable transparent querying of remote repositories with intelligent branch matching and staleness detection.

## 📋 **Epic Summary**

CIDX currently operates in local-only mode, requiring each developer to maintain their own containers and perform individual indexing. This epic introduces a remote mode where CIDX can link to golden repositories on a remote server, providing team-shared indexing with transparent user experience.

The solution implements hybrid architecture supporting both local and remote modes with mutually exclusive operation per repository. Users can initialize remote mode with server credentials, benefit from intelligent git-aware branch matching, and query remote indexes with identical UX to local operation.

## 🏗️ **System Architecture Overview**

### Core Components

**Remote Mode Architecture:**
```
CIDX Client (Remote Mode)
├── CLI Commands (identical UX)
├── API Client Abstraction Layer
│   ├── CIDXRemoteAPIClient (base HTTP client)
│   ├── RepositoryLinkingClient (discovery & linking)
│   └── RemoteQueryClient (semantic search)
├── Credential Management (encrypted storage)
├── Git Topology Service (branch analysis)
└── Configuration (.code-indexer/.remote-config)

CIDX Server (Enhanced)
├── Repository Discovery API (by git URL)
├── Golden Repository Branch Listing
├── Enhanced Query Results (with timestamps)
└── JWT Authentication System
```

**Operational Flow:**
1. **Initialization**: `cidx init --remote <server> --username <user> --password <pass>`
2. **Repository Discovery**: Find matching golden/activated repos by git origin URL
3. **Smart Linking**: Use git merge-base analysis for intelligent branch matching
4. **Transparent Querying**: Route queries to remote server with identical UX
5. **Staleness Detection**: Compare local vs remote file timestamps

### Technology Stack

**Client-Side Technologies:**
- **CLI Framework**: Click (existing) - command routing and context management
- **HTTP Client**: httpx - async HTTP client for API communication
- **Encryption**: PBKDF2 with project-specific key derivation
- **Git Analysis**: GitTopologyService (existing) - merge-base and branch analysis
- **Configuration**: TOML/JSON - encrypted credential storage

**Server-Side Enhancements:**
- **Authentication**: JWT token management with refresh capabilities
- **Repository Discovery**: Git URL-based repository matching
- **Timestamp Collection**: Universal file modification time storage
- **Branch Listing**: Golden repository branch enumeration

## 🎯 **Business Value**

### Team Collaboration Benefits
- **Shared Indexing**: Eliminate duplicate indexing work across team members
- **Golden Repositories**: Centralized, authoritative code indexes for teams
- **Branch Intelligence**: Automatic linking to appropriate remote branches
- **Transparent UX**: No learning curve - identical to local operation

### Performance & Efficiency
- **Zero Local Setup**: No container management or local indexing required
- **Instant Queries**: Immediate access to pre-indexed team repositories  
- **Network Resilience**: Graceful degradation with clear error guidance
- **Staleness Awareness**: File-level detection of potentially outdated matches

### Security & Management
- **Encrypted Credentials**: Project-specific PBKDF2 encryption
- **Token Lifecycle**: Automatic JWT refresh and re-authentication
- **Multi-Project Isolation**: Separate credentials per project/server
- **Server Compatibility**: API version validation and health checks

## 🔧 **Implementation Features**

### Feature 0: API Server Enhancements (PREREQUISITE)
**Priority**: Highest - blocks all client development
**Stories**: 3 server-side enhancements
- Repository discovery endpoint by git origin URL
- Universal timestamp collection for file staleness detection  
- Golden repository branch listing API

### Feature 1: Comprehensive Command Mode Mapping
**Priority**: High - fundamental architecture
**Stories**: 4 command routing and API client stories
- Automatic mode detection and command routing
- Disabled command handling with clear error messages
- Remote-aware status and uninstall command behavior
- Clean API client abstraction layer

### Feature 2: Remote Mode Initialization  
**Priority**: High - entry point for remote functionality
**Stories**: 3 credential and server validation stories
- Remote initialization with mandatory parameters
- PBKDF2 credential encryption with project-specific keys
- Server compatibility and health verification

### Feature 3: Smart Repository Linking
**Priority**: High - core git-aware functionality
**Stories**: 3 intelligent branch matching stories
- Exact branch name matching (primary strategy)
- Git merge-base analysis for branch fallback hierarchy
- Automatic repository activation when no matches exist

### Feature 4: Remote Query Execution
**Priority**: Medium - transparent querying functionality
**Stories**: 3 remote query and authentication stories
- Transparent remote querying with identical UX
- JWT token management with automatic refresh
- Network error handling and graceful degradation

### Feature 5: Stale Match Detection
**Priority**: Medium - data quality assurance
**Stories**: 3 timestamp-based staleness detection stories
- Local vs remote file timestamp comparison
- Timezone-independent UTC timestamp normalization
- Universal staleness detection for both local and remote modes

### Feature 6: Credential Management
**Priority**: Low - lifecycle management
**Stories**: 3 secure credential lifecycle stories
- JWT token lifecycle within API client abstraction
- Credential rotation support with configuration preservation
- Multi-project credential isolation and protection

## 🎯 **Acceptance Criteria**

### Functional Requirements
- ✅ Remote mode initialization with server/username/password (all mandatory)
- ✅ Identical query UX between local and remote modes
- ✅ Intelligent branch matching using git merge-base analysis
- ✅ File-level staleness detection with timestamp comparison
- ✅ Automatic repository activation for new remote repositories
- ✅ JWT token refresh and re-authentication fallback handling
- ✅ Encrypted credential storage with project-specific key derivation

### Non-Functional Requirements
- ✅ Zero impact on existing local mode functionality
- ✅ Mutually exclusive local/remote operation per repository
- ✅ Network error resilience with clear user guidance
- ✅ API version compatibility validation
- ✅ Cross-timezone timestamp accuracy
- ✅ Clean API client architecture (no raw HTTP in business logic)

### Integration Requirements
- ✅ GitTopologyService integration for branch analysis
- ✅ Existing Click CLI framework compatibility
- ✅ Server-side API enhancements completed first
- ✅ Universal timestamp collection for all indexed files
- ✅ QueryResultItem model enhancement with timestamp fields

## 📊 **Success Metrics**

### User Experience Metrics
- **Command Parity**: 100% identical UX between local and remote query operations
- **Setup Time**: Remote mode initialization completable in <60 seconds
- **Error Clarity**: All error messages provide actionable next steps
- **Branch Matching**: >95% success rate for intelligent branch linking

### Performance Metrics  
- **Query Response**: Remote queries complete within 2x local query time
- **Network Resilience**: Graceful degradation on network failures
- **Token Lifecycle**: Automatic refresh prevents authentication interruptions
- **Staleness Detection**: File-level timestamp comparison accuracy >99%

### Security & Reliability Metrics
- **Credential Security**: Project-specific PBKDF2 encryption with 100,000 iterations
- **API Compatibility**: Server version validation prevents incompatible operations
- **Multi-Project Isolation**: Zero credential leakage between projects
- **Error Recovery**: Automatic re-authentication on token expiration

## 🚀 **Implementation Timeline**

### Phase 1: Server Prerequisites (Days 1-6)
- Feature 0: API Server Enhancements (all 3 stories)
- Server-side development and testing
- API endpoint validation and compatibility

### Phase 2: Core Remote Functionality (Days 7-13)
- Feature 1: Command Mode Mapping (4 stories)
- Feature 2: Remote Mode Initialization (3 stories)  
- Feature 3: Smart Repository Linking (3 stories)
- Core remote architecture and linking logic

### Phase 3: Advanced Features (Days 14-20)
- Feature 4: Remote Query Execution (3 stories)
- Feature 5: Stale Match Detection (3 stories)
- Feature 6: Credential Management (3 stories)
- Polish, testing, and documentation

**Total Duration**: 13-20 days
**Critical Path**: Feature 0 completion blocks all client development
**Dependencies**: Server API enhancements must complete before client work begins

## 📋 **Feature Summary**

| Feature | Priority | Stories | Description |
|---------|----------|---------|-------------|
| **Feature 0** | Highest | 3 | API Server Enhancements (prerequisite) |
| **Feature 1** | High | 4 | Comprehensive Command Mode Mapping |
| **Feature 2** | High | 3 | Remote Mode Initialization |
| **Feature 3** | High | 3 | Smart Repository Linking |
| **Feature 4** | Medium | 3 | Remote Query Execution |
| **Feature 5** | Medium | 3 | Stale Match Detection |
| **Feature 6** | Low | 3 | Credential Management |

**Total Stories**: 21 across 7 features
**Implementation Strategy**: API-first with clean client abstraction layers
**Testing Strategy**: E2E tests for both local and remote mode functionality
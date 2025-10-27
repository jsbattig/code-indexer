# Epic: Multi-User CIDX Server

## Epic Overview
**As a** development team working with multiple repositories  
**I want** a centralized CIDX server that allows multiple users to share indexed repositories and run semantic queries via API  
**So that** we can have a single source of truth for code indexing and enable team-wide semantic code search

## Business Value
- Eliminates duplicate indexing across team members
- Provides centralized access to indexed repositories across branches
- Enables API-driven integration with development tools
- Supports role-based access control for repository management
- Allows efficient resource sharing for embedding and vector operations

## Core Requirements
🔑 **CRITICAL SUCCESS FACTOR**: Query functionality is the primary value. No working queries = zero value delivered.

**Context from Previous C# Attempt**: A previous C# implementation was attempted but failed and was reverted back to working commit. The C# version failed for two critical reasons:
1. **Production Code Mocking**: Implementation used mocks and fakes in production code instead of real functionality
2. **Service Account Permissions**: Running as a service under service account caused insurmountable permissions problems - couldn't even make basic index function work

This Python-based approach using FastAPI aims to succeed by: running in user context (not service account), implementing real functionality (no mocks/fakes in production), and using direct Python module access.

**Non-Negotiable Requirements**:
- Server runs in console context (blocking), NOT as a service
- All cidx operations use direct Python module imports, NOT subprocess calls
- Python-based FastAPI implementation (explicitly NOT C#)
- Must handle VoyageAI API key availability (user already has one configured)

**Resource Limits and Constraints**:
- Maximum 20 golden repositories system-wide (configurable)
- Maximum 5 concurrent queries per repository (additional queries queued)
- Global unique namespaces for golden repository names and activated repository aliases
- JWT tokens extend session on API activity (10-minute default expiration)

**Git Repository Support**:
- HTTP/HTTPS for public/open source repositories only
- SSH authentication managed externally (SSH keys, certificates)
- No git credential storage or management within server

---

## Story 1: Cleanup Existing API Attempts
**As a** developer maintaining the codebase  
**I want** to remove previous API implementation attempts and deprecated query options  
**So that** the codebase is clean and ready for the new Python-based server implementation

### Acceptance Criteria
- **Given** there are debug test scripts from previous C# API attempts
- **When** I clean up the codebase
- **Then** remove debug files: `debug/test_async_api_implementation.py`, `debug/test_async_api_no_auth.py`
- **And** remove deprecated semantic query options from CLI: `--semantic-type`, `--semantic-scope`, `--semantic-features`, `--semantic-parent`, `--semantic-only`
- **And** update query help text to remove references to semantic filtering (these were for AST-based chunking)
- **And** ensure all tests pass after cleanup
- **And** create E2E test that verifies deprecated options are completely removed from CLI help and functionality
- **And** E2E test must cleanup: remove any created containers, stop any running services, clean temporary files

---

## Story 2: FastAPI Server Foundation with Authentication
**As a** user of the CIDX server  
**I want** secure authentication with role-based access control  
**So that** I can access appropriate functionality based on my permissions

### Acceptance Criteria
- **Given** a FastAPI server application
- **When** I implement authentication and authorization
- **Then** create JWT-based authentication with 10-minute default token expiration (configurable), extending session on API activity
- **And** support three user roles: admin (full access), power_user (activate repos + query), normal_user (query + list repos)
- **And** store users in `~/.cidx-server/users.json` with hashed passwords
- **And** provide `/auth/login` endpoint accepting username/password, returning JWT token
- **And** require valid JWT token for all API endpoints (global authentication)
- **And** seed initial admin user (admin/admin) during server installation
- **And** create Swagger/OpenAPI documentation accessible via `/docs` endpoint
- **And** users can authenticate via Swagger UI and test all APIs
- **And** upon completion and testing, mark corresponding APIs as ✅ in the Epic API Implementation Table
- **And** create E2E test covering full authentication flow: login with valid/invalid credentials, token validation, role-based access control
- **And** E2E test must cleanup: remove test users from users.json, clear any authentication tokens, reset to initial state

---

## Story 3: User Management APIs
**As an** admin user  
**I want** complete user management capabilities  
**So that** I can control access to the CIDX server

### Acceptance Criteria
- **Given** authenticated admin privileges
- **When** I manage users via API
- **Then** provide CRUD operations for users: `POST /api/admin/users` (create), `GET /api/admin/users` (list), `PUT /api/admin/users/{username}` (update), `DELETE /api/admin/users/{username}` (delete)
- **And** provide `PUT /api/users/change-password` for current user password change
- **And** provide `PUT /api/admin/users/{username}/change-password` for admin to change any user's password
- **And** validate user creation: username uniqueness, password complexity, valid role assignment
- **And** hash all passwords before storage (never store plaintext)
- **And** return appropriate HTTP status codes: 201 (created), 200 (success), 400 (validation error), 404 (not found), 403 (forbidden)
- **And** upon completion and testing, mark corresponding APIs as ✅ in the Epic API Implementation Table
- **And** create E2E test covering complete user lifecycle: create admin user, create power user, create normal user, test CRUD operations, password changes
- **And** E2E test must cleanup: remove all test users from users.json, restore original admin/admin user only

---

## Story 4: Server Installation and Configuration
**As a** system administrator  
**I want** an automated installation process for the CIDX server  
**So that** I can quickly deploy and configure the server

### Acceptance Criteria  
- **Given** the CIDX command line tool
- **When** I run `cidx install-server`
- **Then** find available port starting from 8090 (if busy, try 8091, 8092, etc.)
- **And** report allocated port to user during installation process
- **And** create `~/.cidx-server/` directory structure: `config.json`, `users.json`, `logs/`
- **And** save allocated port in `~/.cidx-server/config.json`
- **And** create startup script at `~/.cidx-server/start-server.sh` with proper port configuration
- **And** seed admin/admin user during installation
- **And** display allocated port and startup instructions to user
- **And** make startup script executable and include full path to Python/virtual environment
- **And** handle case where installation is run multiple times (update existing config)
- **And** create E2E test for complete installation process: run cidx install-server, verify directory structure, verify port allocation, verify startup script, test server startup
- **And** E2E test must cleanup: remove ~/.cidx-server/ directory completely, stop any running server processes

---

## Story 5: Golden Repository Management (Admin Only)
**As an** admin user  
**I want** to register and manage golden repositories  
**So that** they can be shared and activated by other users

### Acceptance Criteria
- **Given** authenticated admin privileges  
- **When** I manage golden repositories
- **Then** provide `POST /api/admin/golden-repos` accepting: name (optional, derived from URL/path if empty), gitUrl (for remote) OR localPath (for local copy)
- **And** enforce global unique naming for golden repositories across all users
- **And** implement background job system for repository operations with job ID return
- **And** clone remote repositories or copy local repositories to `~/.cidx-server/golden-repos/{name}/`
- **And** after cloning/copying, execute workflow: `cidx init --embedding-provider voyage-ai`, `cidx start --force-docker`, verify health with `cidx status --force-docker`, `cidx index --force-docker`, `cidx stop --force-docker`
- **And** golden repository operations are gated (background jobs) to prevent conflicts
- **And** only admin users can perform golden repository operations
- **And** provide `PUT /api/admin/golden-repos/{name}/refresh` for git pull + reindex workflow (background job)
- **And** provide `DELETE /api/admin/golden-repos/{name}` for complete removal including `cidx uninstall --force-docker`  
- **And** provide `GET /api/admin/golden-repos` to list all golden repositories with status
- **And** provide `GET /api/admin/operations/{job-id}/status` for background job status tracking
- **And** all repository operations are gated (one operation per repo at a time) and run in background
- **And** enforce maximum limit of 20 golden repositories system-wide (configurable)
- **And** upon completion and testing, mark corresponding APIs as ✅ in the Epic API Implementation Table

---

## Story 6: Repository Activation System (Power User)
**As a** power user  
**I want** to activate golden repositories for querying  
**So that** I can run semantic searches against specific branches

### Acceptance Criteria
- **Given** authenticated power user privileges and existing golden repositories
- **When** I activate repositories for querying  
- **Then** provide `POST /api/repos/activate` accepting: goldenRepoName, alias, branch (optional, defaults to current branch)
- **And** enforce global unique naming for activated repository aliases across all users
- **And** implement CoW cloning with fallback to regular copy if CoW unavailable
- **And** after CoW cloning/copying, execute: `git checkout {branch}` (return error if branch doesn't exist - do NOT allow branch creation), `cidx fix-config` (reallocate ports and parameters), `cidx start --force-docker`
- **And** activated repos are stored in `~/.cidx-server/activated-repos/{alias}/` directory structure
- **And** implement Copy-on-Write (CoW) cloning when available, fallback to regular copy if CoW not supported
- **And** CoW clone detection should check filesystem type and availability (BTRFS/ZFS preferred)
- **And** implement 10-minute idle timeout (reset on each query) with automatic `cidx stop` but preserve CoW clone
- **And** provide `PUT /api/repos/{alias}/change-branch` accepting new branch name (power user only)
- **And** branch change operation triggers full re-index workflow: shutdown cidx, git checkout new branch (fail if branch doesn't exist), re-index, restart cidx services
- **And** provide `PUT /api/repos/{alias}/refresh` for git pull + reindex on current branch (background job with gating)
- **And** refresh operation uses same workflow as golden repo refresh but for specific activated repo branch
- **And** refresh operations are queued if repo is busy with queries rather than rejected with error
- **And** concurrent queries are allowed during normal operation but fail immediately if refresh operation has write lock
- **And** provide `DELETE /api/repos/{alias}` for deactivation including `cidx uninstall --force-docker`
- **And** provide `GET /api/repos` to list all activated repositories with status and last-used timestamp
- **And** all activation operations return job IDs and run as background jobs
- **And** implement per-repo read-write gating: concurrent queries allowed, exclusive refresh operations
- **And** gating behavior: read operations (queries) fail IMMEDIATELY if write-locked (different from traditional read-write locks)
- **And** write operations (refresh) WAIT for all read operations to complete before acquiring lock
- **And** gating is per-repository (Repo A queries don't block Repo B refresh operations)
- **And** upon completion and testing, mark corresponding APIs as ✅ in the Epic API Implementation Table

---

## Story 7: Semantic Query API
**As a** user with query access  
**I want** to perform semantic searches via API  
**So that** I can find relevant code across activated repositories

### Acceptance Criteria
- **Given** authenticated user with query permissions and activated repositories
- **When** I query code semantically
- **Then** provide `POST /api/query` with complete parameter support (see Query API Specification below)
- **And** translate API parameters to `cidx query` command options (support all current options except deprecated semantic ones)
- **And** execute queries against activated repository using direct Python module imports (not subprocess)
- **And** return structured JSON response with: results array, scores, file paths, matched content, repository context
- **And** implement query queuing system: maximum 5 concurrent queries per repository, additional queries queued for execution
- **And** queries are CPU-intensive operations requiring resource management
- **And** implement query-level gating per repository (fail fast if repo is write-locked for refresh)
- **And** reset activated repository timeout timer on each successful query
- **And** validate repository alias exists and is active before executing query
- **And** handle cidx service startup if repository is stopped due to timeout
- **And** return appropriate errors: 400 (invalid params), 404 (repo not found), 423 (repo locked), 503 (repo not ready)
- **And** upon completion and testing, mark corresponding APIs as ✅ in the Epic API Implementation Table

### Query API Specification

**Endpoint**: `POST /api/query`

**Request Body Parameters**:
```json
{
  "query": "search text",           // REQUIRED: Search query string
  "repoAlias": "my-repo",          // REQUIRED: Alias of activated repository to search
  "limit": 10,                     // OPTIONAL: Number of results to return (default: 10)
  "language": "python",            // OPTIONAL: Filter by programming language
  "path": "*/tests/*",             // OPTIONAL: Filter by file path pattern
  "minScore": 0.8,                 // OPTIONAL: Minimum similarity score (0.0-1.0)
  "accuracy": "balanced",          // OPTIONAL: Search accuracy profile
  "quiet": false                   // OPTIONAL: Quiet mode flag
}
```

**Supported Languages**:
`python`, `javascript`, `typescript`, `java`, `cpp`, `c`, `csharp`, `go`, `rust`, `ruby`, `php`, `shell`, `html`, `css`, `sql`, `swift`, `kotlin`, `scala`, `dart`, `vue`, `pascal`, `delphi`, `markdown`, `json`, `yaml`, `toml`, `text`

**Accuracy Profiles**:
- `fast`: Lower accuracy, faster execution
- `balanced`: Default, good balance of accuracy and speed  
- `high`: Higher accuracy, slower execution

**Response Format**:
```json
{
  "success": true,
  "repoAlias": "my-repo",
  "query": "search text",
  "totalResults": 5,
  "results": [
    {
      "score": 0.95,
      "filePath": "src/services/auth.py",
      "content": "def authenticate_user(username, password):\n    # Implementation here",
      "lineStart": 42,
      "lineEnd": 45,
      "metadata": {
        "fileExtension": "py",
        "language": "python"
      }
    }
  ],
  "searchMetadata": {
    "accuracy": "balanced",
    "language": "python",
    "path": null,
    "minScore": 0.0,
    "executionTimeMs": 150
  }
}
```

**Error Responses**:
- `400 Bad Request`: Invalid parameters or missing required fields
- `404 Not Found`: Repository alias not found or not activated
- `423 Locked`: Repository is locked for refresh operation (fail fast)
- `503 Service Unavailable`: Repository services not ready (e.g., after timeout)

**⚠️ DEPRECATED PARAMETERS (DO NOT IMPLEMENT)**:
- `semanticType`/`type`: Removed with AST-based chunking
- `semanticScope`/`scope`: Removed with AST-based chunking  
- `semanticFeatures`/`features`: Removed with AST-based chunking
- `semanticParent`/`parent`: Removed with AST-based chunking
- `semanticOnly`: Removed with AST-based chunking

---

## Story 8: Background Job Management System
**As a** user performing repository operations  
**I want** reliable background job processing with status tracking  
**So that** I can monitor long-running operations and get results

### Acceptance Criteria
- **Given** any background job operation (clone, refresh, activate, etc.)
- **When** I track job progress
- **Then** implement in-memory job queue with threading for background execution
- **And** return unique job ID immediately (HTTP 202 Accepted) for all background operations
- **And** provide job status via `GET /api/operations/{job-id}/status` returning: jobId, type, status (queued/running/completed/failed), progress, currentStep, startedAt, completedAt, error details
- **And** maintain job status history until server restart (in-memory storage acceptable)
- **And** implement proper per-repository gating to prevent conflicting operations
- **And** on job failure, preserve current state and provide detailed error information
- **And** implement retry capability for refresh operations and query operations
- **And** for other operations (clone, activate, deactivate), preserve evidence for human troubleshooting rather than auto-retry
- **And** queue jobs appropriately when repository is busy rather than rejecting requests
- **And** only admin users can manipulate golden repositories (create, refresh, delete)
- **And** power users can create activated repos and perform queries
- **And** normal users can only perform queries on activated repositories
- **And** ensure thread-safe job status updates and repository state management
- **And** upon completion and testing, mark corresponding APIs as ✅ in the Epic API Implementation Table

---

## Story 9: Server Lifecycle Management
**As a** server operator  
**I want** proper server startup, shutdown, and signal handling  
**So that** I can manage the server safely without data corruption

### Acceptance Criteria
- **Given** a running CIDX server process
- **When** I manage the server lifecycle
- **Then** implement graceful Ctrl+C handling that queues shutdown until all background jobs complete
- **And** during shutdown, stop accepting new API requests (return 503 Service Unavailable)
- **And** provide clear console logging for high-priority events: server startup, shutdown, job failures, authentication failures
- **And** log all operations to `~/.cidx-server/logs/server.log` with rotation
- **And** display server status on startup: allocated port, number of golden repos, active repositories
- **And** validate server configuration and dependencies on startup (VoyageAI key, Docker availability)
- **And** implement basic health check endpoint `GET /health` returning server status and repository counts
- **And** ensure server runs as blocking console process (not daemon) as specified
- **And** upon completion and testing, mark corresponding APIs as ✅ in the Epic API Implementation Table

---

## Story 10: Golden Repository Listing and Status APIs
**As a** user of the CIDX server  
**I want** to discover available repositories and their status  
**So that** I can understand what resources are available for activation and querying

### Acceptance Criteria
- **Given** authenticated user access
- **When** I query repository information
- **Then** provide `GET /api/golden-repos` (available to all users) returning: name, gitUrl/localPath, status, lastUpdated, branches available
- **And** provide `GET /api/repos` returning activated repositories for current user context: alias, goldenRepoName, currentBranch, status (active/stopped), lastUsed, timeoutRemaining
- **And** include repository health status: indexing complete, cidx services status, vector count, last index time
- **And** filter activated repository list based on user permissions (users see only their activations, admins see all)
- **And** provide repository statistics: total files indexed, chunk count, supported languages detected
- **And** return 200 OK with empty arrays when no repositories are available (not 404)
- **And** include pagination support for large repository lists (limit/offset parameters)
- **And** upon completion and testing, mark corresponding APIs as ✅ in the Epic API Implementation Table

---

## Story 11: Testing Infrastructure for Multi-User Server
**As a** developer maintaining the CIDX server  
**I want** comprehensive testing coverage for all server functionality  
**So that** I can ensure reliability and prevent regressions

### Acceptance Criteria
- **Given** the multi-user server implementation
- **When** I run the test suite  
- **Then** create unit tests for: authentication, authorization, user management, job queue, repository gating
- **And** create integration tests for: complete API workflows, background job processing, repository lifecycle management
- **And** create E2E tests for: full user journey from installation to querying, multi-user scenarios, concurrent operations
- **And** test all error conditions: invalid authentication, repository conflicts, job failures, network issues
- **And** validate security: password hashing, JWT validation, role-based access control, input sanitization  
- **And** test server lifecycle: startup, graceful shutdown, signal handling, configuration validation
- **And** ensure tests use isolated environments and don't interfere with existing cidx installations
- **And** include performance tests for concurrent query operations and background job throughput
- **And** create standardized test repository at `tests/fixtures/cidx-test-repo/` with the 10 source files specified in E2E Testing Requirements section
- **And** ensure test repository is committed to version control with realistic git history and multiple branches

---

## Epic Definition of Done
- [x] All stories completed with acceptance criteria met
- [x] FastAPI server with full authentication and authorization
- [x] Complete golden repository management (admin only)
- [x] Repository activation system with branching support (power users)
- [x] Semantic query API supporting all current cidx query parameters
- [x] Reliable background job processing with status tracking
- [x] Graceful server lifecycle management
- [x] Comprehensive API documentation via Swagger/OpenAPI
- [x] Complete test coverage (unit, integration, E2E)
- [x] Installation script and startup automation
- [x] All deprecated query options removed from CLI

## Technical Architecture Notes

### Repository Gating System
```pseudocode
class RepositoryGate:
    read_count = 0
    write_locked = False
    
    acquire_read():
        if write_locked: raise RepositoryLockedException
        read_count += 1
        
    release_read():
        read_count -= 1
        
    acquire_write():
        wait_until(read_count == 0)
        write_locked = True
        
    release_write():
        write_locked = False
```

### Directory Structure
```
~/.cidx-server/
├── config.json          # Server configuration, port allocation
├── users.json           # User database with hashed passwords  
├── logs/
│   └── server.log        # All server operations
├── golden-repos/
│   ├── repo1/            # Golden repository clones
│   └── repo2/
├── activated-repos/
│   ├── user1-alias1/     # CoW clones for activated repos
│   └── user2-alias2/
└── start-server.sh       # Generated startup script
```

### FastAPI Application Structure  
```pseudocode
FastAPI App:
├── /auth/login                          # Authentication
├── /api/admin/users/**                  # User management (admin)
├── /api/admin/golden-repos/**           # Golden repo management (admin)  
├── /api/repos/**                        # Repository activation (power user)
├── /api/query                           # Semantic search (all users)
├── /api/operations/{job-id}/status      # Job status tracking
├── /health                              # Health check
└── /docs                                # Swagger documentation
```

## Breaking Changes
- None (this is a new feature addition)

## Migration Path  
- No migration needed (new functionality)
- Existing cidx installations remain unaffected
- Server installation is opt-in via `cidx install-server`

## Dependencies
- FastAPI framework for API server
- JWT authentication library (PyJWT or similar)
- VoyageAI API key required for embedding provider (user already has this configured)
- Docker/Podman for container management
- CoW filesystem support (BTRFS/ZFS preferred, fallback to regular copy)
- Threading support for background job processing
- Uvicorn ASGI server for FastAPI deployment

## Critical Implementation Context

### Previous C# Implementation Issues
- A C# server was previously attempted but failed due to two critical flaws:
  1. **Production Mocking**: Used mocks and fakes in production code instead of real functionality
  2. **Service Account Permissions**: Service account couldn't access user resources, couldn't even make index function work
- Implementation was reverted back to working commit
- This Python-based approach is the second attempt
- Must avoid pitfalls that caused C# version to fail

### Anti-Patterns to Avoid (Lessons from C# Failure)
- ❌ **NEVER** implement mocks, fakes, or simulation in production code
- ❌ **NEVER** run as system service or with service account permissions
- ❌ **NEVER** use subprocess calls when direct module access is available
- ✅ **ALWAYS** implement real functionality that actually works
- ✅ **ALWAYS** run in user context with proper permissions
- ✅ **ALWAYS** use direct Python module imports for cidx operations

### Server Runtime Requirements
- Server MUST run in console context (blocking the terminal)
- Server is NOT implemented as a system service or daemon
- Use direct Python module imports for all cidx operations
- Never use subprocess calls to cidx commands - use the Python code directly
- Handle Ctrl+C gracefully by queuing shutdown until background jobs complete

### Repository Operation Specifics
- Golden repos: Admin-only, managed in `~/.cidx-server/golden-repos/`
- Activated repos: Power user + admin, CoW cloned to `~/.cidx-server/activated-repos/`
- Branch management: Checkout existing branches only, no branch creation allowed
- Refresh operations: git pull + incremental reindex for specific branch
- Timeout management: 10-minute idle timeout resets on each query, stops services but preserves CoW clone

### Gating System Implementation
- Per-repository read-write locks with non-standard behavior
- Read operations (queries) fail IMMEDIATELY if write-locked
- Write operations (refresh) WAIT for read operations to complete
- Multiple concurrent queries allowed when no write lock
- Repository A operations don't affect Repository B locks

---

## Epic API Implementation Table

Track implementation and testing completion for all server APIs. Mark with ✅ when both implementation AND comprehensive testing are complete.

| API Endpoint | Method | Description | User Role | Story | Status |
|--------------|--------|-------------|-----------|-------|---------|
| **Authentication APIs** |
| `/auth/login` | POST | User authentication, returns JWT token | All | Story 2 | ✅ |
| **User Management APIs** |
| `/api/admin/users` | POST | Create new user | Admin | Story 3 | ✅ |
| `/api/admin/users` | GET | List all users | Admin | Story 3 | ✅ |
| `/api/admin/users/{username}` | PUT | Update user details | Admin | Story 3 | ✅ |
| `/api/admin/users/{username}` | DELETE | Delete user | Admin | Story 3 | ✅ |
| `/api/users/change-password` | PUT | Change current user password | All | Story 3 | ✅ |
| `/api/admin/users/{username}/change-password` | PUT | Admin change user password | Admin | Story 3 | ✅ |
| **Golden Repository Management APIs** |
| `/api/admin/golden-repos` | POST | Register new golden repository | Admin | Story 5 | ✅ |
| `/api/admin/golden-repos` | GET | List golden repositories | Admin | Story 5 | ✅ |
| `/api/admin/golden-repos/{alias}/refresh` | POST | Refresh golden repository | Admin | Story 5 | ✅ |
| `/api/admin/golden-repos/{alias}` | DELETE | Remove golden repository | Admin | Story 5 | ✅ |
| **Repository Activation APIs** |
| `/api/repos/activate` | POST | Activate repository for querying | Power User | Story 6 | ✅ |
| `/api/repos` | GET | List activated repositories | All | Story 6 | ✅ |
| `/api/repos/{alias}` | DELETE | Deactivate repository | Power User, Admin | Story 6 | ✅ |
| `/api/repos/{alias}/branch` | PUT | Change branch on activated repo | Power User, Admin | Story 6 | ✅ |
| **Repository Listing APIs** |
| `/api/repos/available` | GET | List available golden repositories | All | Story 10 | ✅ |
| `/api/repos/golden/{alias}` | GET | Get golden repository details | All | Story 10 | ✅ |
| **Query APIs** |
| `/api/query` | POST | Semantic code search | All | Story 7 | ✅ |
| **Job Management APIs** |
| `/api/jobs/{job-id}` | GET | Get background job status | All | Story 8 | ✅ |
| `/api/jobs` | GET | List user's background jobs | All | Story 8 | ✅ |
| `/api/jobs/{job-id}` | DELETE | Cancel background job | All | Story 8 | ✅ |
| `/api/admin/jobs/cleanup` | DELETE | Admin cleanup old jobs | Admin | Story 8 | ✅ |
| **System APIs** |
| `/health` | GET | Server health check | All | Story 9 | ✅ |
| `/docs` | GET | Swagger/OpenAPI documentation | All | Story 2 | ✅ |

### API Implementation Guidelines

**Completion Criteria for ✅ Status**:
1. **Implementation**: Full working implementation with all business logic
2. **Testing**: Comprehensive unit, integration, and E2E tests passing
3. **Documentation**: API documented in Swagger/OpenAPI
4. **Error Handling**: Proper HTTP status codes and error responses
5. **Security**: Authentication, authorization, and input validation
6. **Integration**: Successfully integrated with background job system and repository gating

**Status Legend**:
- ⭕ **Not Started**: API not yet implemented
- 🔄 **In Progress**: Implementation started but not complete
- ✅ **Complete**: Implementation AND testing both finished

### Implementation Order Recommendation
1. Start with authentication foundation (Story 2)
2. Implement user management (Story 3) 
3. Build golden repository management (Story 5)
4. Add repository activation system (Story 6)
5. Implement semantic query API (Story 7) - **CRITICAL PATH**
6. Complete background job management (Story 8)
7. Add system APIs and repository listing (Stories 9, 10)

**Critical Success Metric**: Query API (`/api/query`) must be fully functional - this is the primary value delivery.

---

## Comprehensive E2E Testing Requirements

### Test Repository Setup (tests/fixtures/cidx-test-repo)

**MANDATORY**: All E2E tests must use a standardized test repository located in the project at `tests/fixtures/cidx-test-repo/` containing ~10 real source code files, then copy to `/tmp/cidx-test-repo-{test-id}` for test isolation:

**Project Structure**:
```
tests/fixtures/cidx-test-repo/       # Version controlled test repository
├── .git/                           # Real git repository (committed to main repo)
├── README.md                       # Project documentation
├── src/
│   ├── auth.py                    # Python authentication module
│   ├── database.js                # JavaScript database utilities  
│   ├── UserService.java           # Java user service class
│   ├── api.ts                     # TypeScript API definitions
│   ├── main.go                    # Go application entry point
│   ├── lib.rs                     # Rust library code
│   ├── utils.cpp                  # C++ utility functions
│   └── config.json                # Configuration file
├── scripts/
│   └── deploy.sh                  # Shell deployment script
└── docs/
    └── api.md                     # API documentation
```

**Test Execution Pattern**:
```pseudocode
@setup_e2e_test
def prepare_test_repository():
    test_id = generate_unique_id()
    source_repo = "tests/fixtures/cidx-test-repo"
    temp_repo = f"/tmp/cidx-test-repo-{test_id}"
    
    # Copy fixture to isolated temp location
    copy_directory(source_repo, temp_repo)
    
    # Initialize as real git repo if needed
    run_command("git init", temp_repo)
    run_command("git add .", temp_repo) 
    run_command("git commit -m 'Test repository'", temp_repo)
    
    # Create test branches
    run_command("git checkout -b feature/auth", temp_repo)
    run_command("git checkout -b dev", temp_repo)
    run_command("git checkout main", temp_repo)
    
    return temp_repo
```

### E2E Test Repository Requirements

**Repository Setup**:
- **Source Location**: `tests/fixtures/cidx-test-repo/` (version controlled in main repo)
- **Test Location**: `/tmp/cidx-test-repo-{test-id}` (copied during test setup for isolation)
- Real git repository with multiple branches: `main`, `feature/auth`, `dev`  
- Commit history with meaningful messages
- Files contain realistic code patterns for semantic search testing
- Total repository size: ~50KB (small enough for fast cloning)

**File Content Requirements**:
- **auth.py**: Authentication functions, password hashing, JWT handling
- **database.js**: Database connection, query functions, error handling
- **UserService.java**: User CRUD operations, validation methods
- **api.ts**: REST API type definitions, request/response interfaces
- **main.go**: HTTP server setup, routing, middleware
- **lib.rs**: Data structures, algorithms, utility functions
- **utils.cpp**: String manipulation, file I/O operations
- **deploy.sh**: Docker commands, environment setup
- **config.json**: Server configuration, database settings
- **README.md**: Project description, setup instructions

### Mandatory E2E Test Patterns

**Test Lifecycle**:
1. **Setup**: Copy `tests/fixtures/cidx-test-repo/` to `/tmp/cidx-test-repo-{test-id}` for isolation
2. **Execute**: Run complete workflow (register → activate → query → cleanup)
3. **Teardown**: MANDATORY complete cleanup (see below)

**Repository Operations Testing**:
- Golden repo registration from `/tmp/cidx-test-repo-{test-id}`
- Repository activation with branch switching
- Query operations across all supported languages
- Concurrent operations and gating behavior
- Error scenarios (invalid branches, locked repos)

### MANDATORY Cleanup Requirements

**🚨 CRITICAL**: ALL E2E tests MUST include comprehensive teardown that prevents dangling containers:

```pseudocode
@teardown
def cleanup_e2e_test():
    // 1. Stop and remove all cidx services
    for repo in activated_repos:
        run_command("cidx uninstall --force-docker", repo.directory)
    
    for repo in golden_repos:
        run_command("cidx uninstall --force-docker", repo.directory)
    
    // 2. Remove repository directories
    remove_directory("~/.cidx-server/golden-repos/")
    remove_directory("~/.cidx-server/activated-repos/")
    
    // 3. Stop server process
    terminate_server_process()
    
    // 4. Remove server installation
    remove_directory("~/.cidx-server/")
    
    // 5. Remove test repository
    remove_directory(f"/tmp/cidx-test-repo-{test_id}")
    
    // 6. Verify no dangling containers
    containers = run_command("docker ps -q --filter name=cidx")
    assert containers.empty(), "Dangling cidx containers found!"
    
    volumes = run_command("docker volume ls -q --filter name=cidx")
    assert volumes.empty(), "Dangling cidx volumes found!"
```

### Story-Specific E2E Requirements

**Story 1 (Cleanup)**: Verify deprecated options completely removed from CLI
**Story 2 (Authentication)**: Full auth flow with token validation  
**Story 3 (User Management)**: Complete user CRUD lifecycle
**Story 4 (Installation)**: Server installation and startup validation
**Story 5 (Golden Repos)**: Complete golden repo workflow using `/tmp/cidx-test-repo`
**Story 6 (Activation)**: Repository activation with branch management
**Story 7 (Query API)**: Semantic queries across all languages in test repo
**Story 8 (Background Jobs)**: Concurrent job processing and status tracking
**Story 9 (Server Lifecycle)**: Graceful startup/shutdown with job completion
**Story 10 (Repository Listing)**: Multi-repo listing with different user roles
**Story 11 (Testing Infrastructure)**: Meta-test validation

### E2E Test Success Criteria

**Container Verification**:
- Before test: Record existing containers
- After cleanup: Verify no new containers remain
- Test FAILS if any cidx containers are left running

**Process Verification**:
- Verify server process completely terminated
- No background jobs running after cleanup
- All ports released and available

**File System Verification**:
- `~/.cidx-server/` completely removed
- `/tmp/cidx-test-repo-{test-id}` removed
- No temporary files or logs remaining

**Integration Verification**:
- Test complete workflows, not individual components
- Verify real cidx operations (no mocking in E2E tests)
- Validate actual query results against test repository content
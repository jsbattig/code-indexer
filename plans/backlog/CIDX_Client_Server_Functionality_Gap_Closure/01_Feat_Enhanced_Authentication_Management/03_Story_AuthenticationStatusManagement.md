# Story: Authentication Status Management

[Conversation Reference: "Token status and credential management"]

## Story Overview

**Objective**: Implement comprehensive authentication status monitoring and credential management capabilities, providing users with visibility into their authentication state and token lifecycle management.

**User Value**: Users can monitor their authentication status, understand token expiration, and manage their credential lifecycle effectively, ensuring reliable access to authenticated operations.

**Acceptance Criteria Summary**: Complete authentication status visibility with token management, credential validation, and session monitoring capabilities.

## Acceptance Criteria

### AC1: Authentication Status Display
**Scenario**: User checks current authentication status
```gherkin
Given I am authenticated with valid credentials
When I execute "cidx auth status"
Then the system should display "Authenticated: Yes"
And display "Username: <current_username>"
And display "Role: <user_role>"
And display "Token expires: <expiration_datetime>"
And display "Server: <server_url>"
And display "Status: Active"

Given I am not authenticated
When I execute "cidx auth status"
Then the system should display "Authenticated: No"
And display "Status: Not logged in"
And suggest "Use 'cidx auth login' to authenticate"
```

**Technical Requirements**:
- [x] Implement `cidx auth status` command with no parameters
- [x] Parse stored JWT token to extract user information
- [x] Calculate and display token expiration time in human-readable format
- [x] Show current server URL from configuration
- [x] Display user role information from token claims
- [x] Handle cases where no credentials are stored

### AC2: Token Validity Verification
**Scenario**: System validates token status and handles expiration
```gherkin
Given I have stored credentials with valid token
When I execute "cidx auth status"
Then the system should verify token validity with server
And display "Token status: Valid"
And show remaining time until expiration

Given I have stored credentials with expired token
When I execute "cidx auth status"
Then the system should detect token expiration
And display "Token status: Expired"
And automatically attempt token refresh if refresh token available
And display refresh result

Given token refresh is successful
Then the system should display "Token status: Refreshed"
And update stored credentials with new token
And show new expiration time

Given token refresh fails
Then the system should display "Token status: Expired (refresh failed)"
And suggest "Use 'cidx auth login' to re-authenticate"
And clear invalid credentials
```

**Technical Requirements**:
- [x] Implement JWT token expiration checking
- [x] Attempt automatic token refresh using refresh token
- [x] Validate token with server when network available
- [x] Update stored credentials after successful refresh
- [x] Clear invalid credentials when refresh fails
- [x] Display clear status for each token state

### AC3: Detailed Credential Information
**Scenario**: User requests detailed authentication information
```gherkin
Given I am authenticated with valid credentials
When I execute "cidx auth status --verbose"
Then the system should display all basic status information
And additionally display "Token issued: <issue_datetime>"
And display "Last refreshed: <refresh_datetime>"
And display "Refresh token expires: <refresh_expiration>"
And display "Permissions: <user_permissions>"
And display "Server version: <server_version>"
And display "Connection status: <connectivity_status>"
```

**Technical Requirements**:
- [x] Add `--verbose` option to status command
- [x] Extract detailed information from JWT token claims
- [x] Show token issuance and refresh timestamps
- [x] Display refresh token expiration if available
- [x] Show user permissions/roles from token
- [x] Test server connectivity and display status
- [x] Include server version information if available

### AC4: Credential Health Monitoring
**Scenario**: System monitors and reports credential health
```gherkin
Given I have stored credentials
When I execute "cidx auth status --health"
Then the system should check credential file integrity
And verify encryption key availability
And test server connectivity
And validate token signature
And display "Credential health: Healthy" if all checks pass
And display specific issues if any checks fail

Given my credential file is corrupted
When I execute "cidx auth status --health"
Then the system should display "Credential health: Corrupted"
And display "Issue: Credential file cannot be decrypted"
And suggest "Use 'cidx auth logout' and 'cidx auth login' to recover"

Given the server is unreachable
When I execute "cidx auth status --health"
Then the system should display "Credential health: Cannot verify"
And display "Issue: Server unreachable for token validation"
And suggest checking network connectivity
```

**Technical Requirements**:
- [x] Add `--health` option for comprehensive credential checking
- [x] Verify credential file encryption and decryption
- [x] Test server connectivity for token validation
- [x] Validate JWT token structure and signature
- [x] Check credential file permissions and integrity
- [x] Provide specific diagnostics for each failure type
- [x] Suggest appropriate recovery actions

### AC5: Token Lifecycle Management
**Scenario**: User manages token lifecycle operations
```gherkin
Given I am authenticated with stored credentials
When I execute "cidx auth refresh"
Then the system should attempt to refresh the current token
And display "Token refreshed successfully" if refresh succeeds
And update stored credentials with new token
And display new expiration time

Given refresh token is expired or invalid
When I execute "cidx auth refresh"
Then the system should display "Token refresh failed: Refresh token expired"
And suggest "Use 'cidx auth login' to re-authenticate"
And clear invalid credentials

Given I want to validate credentials without displaying status
When I execute "cidx auth validate"
Then the system should silently validate credentials
And return exit code 0 for valid credentials
And return exit code 1 for invalid credentials
And not display any output unless --verbose specified
```

**Technical Requirements**:
- [x] Implement `cidx auth refresh` command for manual token refresh
- [x] Implement `cidx auth validate` command for silent validation
- [x] Handle refresh token expiration gracefully
- [x] Support silent validation for scripting use cases
- [x] Return appropriate exit codes for automation
- [x] Update credentials after successful refresh operations

## Technical Implementation Details

### Command Structure Extension
```python
@auth.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.option("--health", is_flag=True, help="Check credential health")
def status(verbose: bool, health: bool):
    """Display current authentication status."""

@auth.command()
def refresh():
    """Manually refresh authentication token."""

@auth.command()
@click.option("--verbose", "-v", is_flag=True, help="Show validation details")
def validate(verbose: bool):
    """Validate current credentials (silent by default)."""
```

### Authentication Status Data Model
```python
@dataclass
class AuthStatus:
    authenticated: bool
    username: Optional[str]
    role: Optional[str]
    token_valid: bool
    token_expires: Optional[datetime]
    refresh_expires: Optional[datetime]
    server_url: str
    last_refreshed: Optional[datetime]
    permissions: List[str]

@dataclass
class CredentialHealth:
    healthy: bool
    issues: List[str]
    encryption_valid: bool
    server_reachable: bool
    token_signature_valid: bool
    file_permissions_correct: bool
```

### Token Management Operations
```python
class AuthAPIClient(CIDXRemoteAPIClient):
    def get_auth_status(self) -> AuthStatus:
        """Get current authentication status with token validation."""

    def refresh_token(self) -> RefreshResponse:
        """Refresh current authentication token."""

    def validate_credentials(self) -> bool:
        """Silently validate current credentials."""

    def check_credential_health(self) -> CredentialHealth:
        """Comprehensive credential health check."""
```

## User Experience Design

### Status Display Format
```
CIDX Authentication Status
==========================
Authenticated: Yes
Username: john.doe
Role: user
Status: Active

Token Information:
  Issued: 2024-01-15 10:30:00
  Expires: 2024-01-15 18:30:00 (in 5 hours 23 minutes)
  Last refreshed: 2024-01-15 14:15:00

Server: https://cidx.example.com
Connection: Online
```

### Health Check Display Format
```
CIDX Credential Health Check
============================
Overall Health: Healthy ✓

Checks Performed:
  ✓ Credential file encryption
  ✓ Token signature validation
  ✓ Server connectivity
  ✓ File permissions
  ✓ Refresh token validity

All credential components are functioning properly.
```

## Testing Requirements

### Unit Test Coverage
- [x] JWT token parsing and validation logic
- [x] Token expiration calculation and formatting
- [x] Credential health checking algorithms
- [x] Status display formatting and output
- [x] Silent validation return code logic

### Integration Test Coverage
- [x] End-to-end status checking with server validation
- [x] Token refresh workflow testing
- [x] Server connectivity testing and error handling
- [x] Credential corruption recovery testing
- [x] Health check comprehensive validation

### Security Test Coverage
- [x] Token information display security (no sensitive data exposure)
- [x] Credential validation without information disclosure
- [x] Health check security (no credential leakage)
- [x] Silent validation security for automation use

## Performance Requirements

### Response Time Targets
- Status display: <1 second for cached information
- Status with server validation: <3 seconds
- Health check: <5 seconds for comprehensive check
- Token refresh: <3 seconds for successful refresh
- Silent validation: <2 seconds for automation use

### Resource Requirements
- Memory usage: <5MB additional for status operations
- Disk I/O: Minimal for credential file access
- Network usage: Only for server validation when requested

## Error Handling Specifications

### User-Friendly Error Messages
```
Authentication status unavailable: Credential file corrupted
Token validation failed: Server returned authentication error
Health check incomplete: Unable to reach server for validation
Refresh failed: Refresh token has expired
Credential access denied: Insufficient file permissions
```

### Silent Operation Support
- Silent validation mode for scripting and automation
- Appropriate exit codes for success/failure conditions
- Optional verbose output for debugging
- Consistent behavior across different error conditions

## Definition of Done

### Functional Completion
- [x] Status command with basic and verbose modes implemented
- [x] Health check functionality working comprehensively
- [x] Token refresh command operational
- [x] Silent validation for automation support
- [x] Comprehensive error handling for all scenarios

### Quality Validation
- [x] >95% test coverage for status and credential management
- [x] Performance benchmarks met for all operations
- [x] User experience validated through testing
- [x] Silent operation modes working for automation
- [x] Error scenarios properly handled and tested

### Integration Readiness
- [x] Status information supports other features' authentication checks
- [x] Health monitoring provides operational insight
- [x] Token management ready for long-running operations
- [x] Silent validation enables automation and scripting

---

**Story Points**: 3
**Priority**: Medium (Important for operational visibility)
**Dependencies**: Authentication commands (Story 1) and password management (Story 2)
**Success Metric**: Users have complete visibility into authentication state with operational management capabilities
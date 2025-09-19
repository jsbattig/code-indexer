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
- [ ] Implement `cidx auth status` command with no parameters
- [ ] Parse stored JWT token to extract user information
- [ ] Calculate and display token expiration time in human-readable format
- [ ] Show current server URL from configuration
- [ ] Display user role information from token claims
- [ ] Handle cases where no credentials are stored

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
- [ ] Implement JWT token expiration checking
- [ ] Attempt automatic token refresh using refresh token
- [ ] Validate token with server when network available
- [ ] Update stored credentials after successful refresh
- [ ] Clear invalid credentials when refresh fails
- [ ] Display clear status for each token state

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
- [ ] Add `--verbose` option to status command
- [ ] Extract detailed information from JWT token claims
- [ ] Show token issuance and refresh timestamps
- [ ] Display refresh token expiration if available
- [ ] Show user permissions/roles from token
- [ ] Test server connectivity and display status
- [ ] Include server version information if available

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
- [ ] Add `--health` option for comprehensive credential checking
- [ ] Verify credential file encryption and decryption
- [ ] Test server connectivity for token validation
- [ ] Validate JWT token structure and signature
- [ ] Check credential file permissions and integrity
- [ ] Provide specific diagnostics for each failure type
- [ ] Suggest appropriate recovery actions

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
- [ ] Implement `cidx auth refresh` command for manual token refresh
- [ ] Implement `cidx auth validate` command for silent validation
- [ ] Handle refresh token expiration gracefully
- [ ] Support silent validation for scripting use cases
- [ ] Return appropriate exit codes for automation
- [ ] Update credentials after successful refresh operations

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
- [ ] JWT token parsing and validation logic
- [ ] Token expiration calculation and formatting
- [ ] Credential health checking algorithms
- [ ] Status display formatting and output
- [ ] Silent validation return code logic

### Integration Test Coverage
- [ ] End-to-end status checking with server validation
- [ ] Token refresh workflow testing
- [ ] Server connectivity testing and error handling
- [ ] Credential corruption recovery testing
- [ ] Health check comprehensive validation

### Security Test Coverage
- [ ] Token information display security (no sensitive data exposure)
- [ ] Credential validation without information disclosure
- [ ] Health check security (no credential leakage)
- [ ] Silent validation security for automation use

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
- [ ] Status command with basic and verbose modes implemented
- [ ] Health check functionality working comprehensively
- [ ] Token refresh command operational
- [ ] Silent validation for automation support
- [ ] Comprehensive error handling for all scenarios

### Quality Validation
- [ ] >95% test coverage for status and credential management
- [ ] Performance benchmarks met for all operations
- [ ] User experience validated through testing
- [ ] Silent operation modes working for automation
- [ ] Error scenarios properly handled and tested

### Integration Readiness
- [ ] Status information supports other features' authentication checks
- [ ] Health monitoring provides operational insight
- [ ] Token management ready for long-running operations
- [ ] Silent validation enables automation and scripting

---

**Story Points**: 3
**Priority**: Medium (Important for operational visibility)
**Dependencies**: Authentication commands (Story 1) and password management (Story 2)
**Success Metric**: Users have complete visibility into authentication state with operational management capabilities
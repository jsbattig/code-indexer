# Story: User Management Operations

[Conversation Reference: "Update, delete, and manage users" - Context: User role updates and deletion]

## Story Overview

**Objective**: Implement CLI commands for complete user lifecycle management including listing, updating, and deleting user accounts.

**User Value**: Administrators can manage existing users, update their permissions, and perform user account maintenance through CLI commands.

**Acceptance Criteria**:
- [ ] `cidx admin users list` command lists all users
- [ ] `cidx admin users show <username>` displays detailed user information
- [ ] `cidx admin users update <username>` allows role and status updates
- [ ] `cidx admin users delete <username>` removes user accounts with confirmation
- [ ] Uses appropriate server endpoints for each operation
- [ ] Requires admin privileges for all operations

## Technical Implementation

### CLI Command Structure
```bash
cidx admin users list [--role ROLE] [--status STATUS]
cidx admin users show <username>
cidx admin users update <username> [--role ROLE] [--active true|false]
cidx admin users delete <username> [--force]
```

### API Integration
- **List Endpoint**: GET `/api/admin/users`
- **Update Endpoint**: PUT `/api/admin/users/{username}`
- **Delete Endpoint**: DELETE `/api/admin/users/{username}`
- **Client**: `AdminAPIClient` methods for each operation
- **Authentication**: Requires admin JWT token

### Safety Features
- Confirmation prompts for destructive operations
- User existence validation before operations
- Self-modification prevention (admin can't delete themselves)
- Clear feedback on operation success/failure

## Definition of Done
- [ ] All user management commands implemented
- [ ] API client methods created with proper error handling
- [ ] Safety checks prevent accidental operations
- [ ] User listing with filtering functionality
- [ ] Admin privilege validation for all operations
- [ ] Unit tests cover all operations and edge cases (>90% coverage)
- [ ] Integration tests validate complete user management workflow

---

**Story Points**: 8
**Dependencies**: User creation functionality must be implemented first
**Risk Level**: High - destructive operations require careful validation
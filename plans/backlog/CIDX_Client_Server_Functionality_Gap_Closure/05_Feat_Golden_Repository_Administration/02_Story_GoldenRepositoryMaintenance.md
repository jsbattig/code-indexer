# Story: Golden Repository Maintenance

[Conversation Reference: "Repository refresh and re-indexing" - Context: Golden repository refresh operations]

## Story Overview

**Objective**: Implement CLI commands for administrators to refresh and maintain golden repositories through available server endpoints.

**User Value**: Administrators can refresh repository content and trigger re-indexing operations to keep repositories up-to-date with their source.

**Acceptance Criteria**:
- [ ] `cidx admin repos refresh <alias>` command triggers repository refresh
- [ ] `cidx admin repos list` command lists golden repositories
- [ ] Support for viewing repository details and status
- [ ] Automatic job creation for refresh operations
- [ ] Uses appropriate server endpoints for repository maintenance
- [ ] Requires admin privileges for execution

## Technical Implementation

### CLI Command Structure
```bash
cidx admin repos list
cidx admin repos show <alias>
cidx admin repos refresh <alias>
```

### API Integration
- **List Endpoint**: GET `/api/admin/golden-repos`
- **Refresh Endpoint**: POST `/api/admin/golden-repos/{alias}/refresh`
- **Client**: `AdminAPIClient` methods for repository operations
- **Authentication**: Requires admin JWT token
- **Response**: Job ID for tracking refresh progress

### Repository Information Display
- Repository alias and Git URL
- Last refresh timestamp
- Current status and health
- Associated job status if applicable

## Definition of Done
- [ ] List command shows all golden repositories
- [ ] Show command displays detailed repository information
- [ ] Refresh command triggers repository update with job tracking
- [ ] API client methods created with proper error handling
- [ ] Admin privilege validation for all operations
- [ ] Unit tests cover all operations and edge cases (>90% coverage)
- [ ] Integration test validates repository maintenance workflow

---

**Story Points**: 5
**Dependencies**: Golden repository creation must be functional
**Risk Level**: Medium - refresh operations can be resource intensive
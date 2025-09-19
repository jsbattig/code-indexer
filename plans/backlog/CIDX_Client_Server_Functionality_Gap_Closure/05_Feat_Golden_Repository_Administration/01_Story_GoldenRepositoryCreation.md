# Story: Golden Repository Creation

[Conversation Reference: "Golden repository addition from Git URLs" - Context: Repository management through Git URL addition]

## Story Overview

**Objective**: Implement CLI commands for administrators to add new golden repositories from Git URLs through the server API.

**User Value**: Administrators can add new repositories to the system for indexing and make them available to users for activation.

**Acceptance Criteria**:
- [ ] `cidx admin repos add` command adds golden repositories from Git URLs
- [ ] Support for various Git URL formats (https, ssh)
- [ ] Repository alias assignment for user-friendly references
- [ ] Automatic job creation for repository cloning and indexing
- [ ] Uses POST /api/admin/golden-repos endpoint
- [ ] Requires admin privileges for execution

## Technical Implementation

### CLI Command Structure
```bash
cidx admin repos add <git_url> <alias> [--description DESC]
```

### API Integration
- **Endpoint**: POST `/api/admin/golden-repos`
- **Client**: `AdminAPIClient.add_golden_repository()`
- **Authentication**: Requires admin JWT token
- **Response**: Job ID for tracking repository addition progress

### Input Validation
- Git URL format validation
- Alias uniqueness checking
- Repository accessibility validation
- Description length limits

### Job Integration
- Repository addition creates background job
- Job ID returned for progress tracking
- Integration with job monitoring commands

## Definition of Done
- [ ] Add command implemented with URL and alias validation
- [ ] API client method created with error handling
- [ ] Job creation and tracking integration
- [ ] Git URL format validation implemented
- [ ] Admin privilege checking implemented
- [ ] Unit tests cover validation and API integration (>90% coverage)
- [ ] Integration test validates repository addition workflow

---

**Story Points**: 5
**Dependencies**: Job monitoring functionality should be available for progress tracking
**Risk Level**: Medium - requires Git URL validation and job integration
# Story: Golden Repository Cleanup

[Conversation Reference: "Repository deletion and cleanup" - Context: Golden repository deletion operations]

## Story Overview

**Objective**: Implement CLI commands for administrators to safely delete golden repositories with proper cleanup procedures.

**User Value**: Administrators can remove outdated or unwanted repositories from the system while ensuring proper cleanup of associated resources.

**Acceptance Criteria**:
- [ ] `cidx admin repos delete <alias>` command removes golden repositories
- [ ] Confirmation prompt for destructive operations
- [ ] Validation that repository is not actively being used
- [ ] Complete cleanup of repository data and associations
- [ ] Uses DELETE /api/admin/golden-repos/{alias} endpoint
- [ ] Requires admin privileges for execution

## Technical Implementation

### CLI Command Structure
```bash
cidx admin repos delete <alias> [--force]
```

### API Integration
- **Endpoint**: DELETE `/api/admin/golden-repos/{alias}`
- **Client**: `AdminAPIClient.delete_golden_repository()`
- **Authentication**: Requires admin JWT token
- **Response**: 204 No Content on successful deletion

### Safety Features
- Confirmation prompt unless `--force` flag used
- Repository existence validation
- Check for active users with activated repositories
- Clear feedback on deletion success/failure

### Cleanup Validation
- Verify repository alias exists before deletion
- Warning if repository has activated instances
- Complete removal confirmation

## Definition of Done
- [ ] Delete command implemented with confirmation prompt
- [ ] API client method created with error handling
- [ ] Safety checks prevent accidental deletions
- [ ] Repository usage validation before deletion
- [ ] Admin privilege checking implemented
- [ ] Unit tests cover validation and API integration (>90% coverage)
- [ ] Integration test validates repository deletion workflow

---

**Story Points**: 3
**Dependencies**: Repository listing functionality must be available for validation
**Risk Level**: High - destructive operation requiring careful validation
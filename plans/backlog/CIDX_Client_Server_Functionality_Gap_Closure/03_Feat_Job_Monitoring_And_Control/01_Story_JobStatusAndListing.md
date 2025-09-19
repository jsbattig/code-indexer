# Story: Job Status and Listing

[Conversation Reference: "List and monitor background jobs" - Context: Background job visibility and status checking]

## Story Overview

**Objective**: Implement CLI commands to list and monitor background jobs with filtering capabilities, providing visibility into running operations.

**User Value**: Users can see what background operations are running and their current status, enabling better understanding of system activity.

**Acceptance Criteria**:
- [ ] `cidx jobs list` command lists all jobs with status
- [ ] Jobs can be filtered by status (running, completed, failed, cancelled)
- [ ] Job listing shows job ID, type, status, progress, and started time
- [ ] Command integrates with existing CLI error handling patterns
- [ ] Uses GET /api/jobs endpoint for job listing

## Technical Implementation

### CLI Command Structure
```bash
cidx jobs list [--status STATUS] [--limit N]
```

### API Integration
- **Endpoint**: GET `/api/jobs`
- **Client**: `JobsAPIClient.list_jobs()`
- **Authentication**: Requires valid JWT token

### Data Display Format
```
Job ID          Type              Status    Progress  Started
job_123456      repo_activation   running   45%       2 min ago
job_789012      golden_repo_sync  completed 100%      5 min ago
```

## Definition of Done
- [ ] Command implemented and integrated into CLI
- [ ] API client method created with proper error handling
- [ ] Job filtering works correctly
- [ ] Progress display formatted appropriately
- [ ] Unit tests cover success and error scenarios (>90% coverage)
- [ ] Integration test validates end-to-end functionality

---

**Story Points**: 3
**Dependencies**: Authentication commands must be functional
**Risk Level**: Low - straightforward API integration
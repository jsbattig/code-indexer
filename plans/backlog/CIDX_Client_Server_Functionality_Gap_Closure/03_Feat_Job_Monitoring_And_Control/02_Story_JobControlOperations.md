# Story: Job Control Operations

[Conversation Reference: "Cancel and manage job execution" - Context: Job cancellation capabilities]

## Story Overview

**Objective**: Implement CLI commands to control job execution, specifically job cancellation through the available server endpoint.

**User Value**: Users can cancel long-running operations when needed, providing control over system resources and job execution.

**Acceptance Criteria**:
- [ ] `cidx jobs cancel <job_id>` command cancels specified job
- [ ] `cidx jobs status <job_id>` command shows detailed job status
- [ ] Cancellation provides confirmation prompt for safety
- [ ] Commands provide appropriate success/error feedback
- [ ] Uses DELETE /api/jobs/{job_id} endpoint for cancellation
- [ ] Uses GET /api/jobs/{job_id} endpoint for detailed status

## Technical Implementation

### CLI Command Structure
```bash
cidx jobs cancel <job_id> [--force]
cidx jobs status <job_id>
```

### API Integration
- **Cancel Endpoint**: DELETE `/api/jobs/{job_id}`
- **Status Endpoint**: GET `/api/jobs/{job_id}`
- **Client**: `JobsAPIClient.cancel_job()` and `JobsAPIClient.get_job_status()`
- **Authentication**: Requires valid JWT token

### Safety Features
- Confirmation prompt unless `--force` flag used
- Clear feedback on cancellation success/failure
- Job status validation before cancellation

## Definition of Done
- [ ] Cancel command implemented with confirmation prompt
- [ ] Status command shows detailed job information
- [ ] API client methods created with proper error handling
- [ ] Safety checks prevent accidental cancellations
- [ ] Unit tests cover success, error, and edge cases (>90% coverage)
- [ ] Integration test validates cancellation workflow

---

**Story Points**: 5
**Dependencies**: Job listing functionality must be implemented first
**Risk Level**: Medium - requires careful handling of job state changes
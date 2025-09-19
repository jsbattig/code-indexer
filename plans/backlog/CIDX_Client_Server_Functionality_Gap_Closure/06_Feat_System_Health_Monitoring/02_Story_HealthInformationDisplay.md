# Story: Health Information Display

[Conversation Reference: "Detailed health checks" - Context: Comprehensive system diagnostics from available endpoints]

## Story Overview

**Objective**: Implement CLI commands to display detailed health information using both available health endpoints for comprehensive system visibility.

**User Value**: Users can see detailed system health status from both available endpoints, providing deeper insight into system components and status.

**Acceptance Criteria**:
- [ ] Enhanced health display combining both endpoints
- [ ] Detailed system component status information
- [ ] Health information formatting for readability
- [ ] Uses both GET /health and GET /api/system/health endpoints
- [ ] Comparison between basic and detailed health data

## Technical Implementation

### CLI Command Enhancement
```bash
cidx system health --detailed
```

### API Integration
- **Basic Endpoint**: GET `/health`
- **Detailed Endpoint**: GET `/api/system/health`
- **Client**: `SystemAPIClient.get_detailed_health()`
- **Authentication**: Requires valid JWT token for detailed endpoint

### Health Information Display
```
=== System Health Status ===
Overall Status: OK
Response Time: 45ms

=== Detailed Component Status ===
Database: OK
Vector Store: OK
Container Services: OK
Authentication: OK

=== System Information ===
Version: 1.0.0
Uptime: 2 days, 3 hours
Active Jobs: 2
```

### Information Aggregation
- Combine data from both health endpoints
- Show comprehensive system status
- Highlight any component issues or warnings

## Definition of Done
- [ ] Detailed health command implemented
- [ ] API client methods for both endpoints created
- [ ] Health information properly formatted and displayed
- [ ] Component status clearly presented
- [ ] Error handling for endpoint failures
- [ ] Unit tests cover both endpoints and formatting (>90% coverage)
- [ ] Integration test validates detailed health display

---

**Story Points**: 3
**Dependencies**: Basic health check functionality must be implemented first
**Risk Level**: Low - read-only health information display
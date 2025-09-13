# Story: Implement Global Error Handler

## User Story
As an **API consumer**, I want **consistent error responses across all endpoints** so that **I can handle errors predictably in my client applications**.

## Problem Context
Currently, different endpoints handle errors differently, leading to inconsistent status codes and response formats. Unhandled exceptions result in generic 500 errors that provide no useful information.

## Acceptance Criteria

### Scenario 1: Validation Error Handling
```gherkin
Given an API endpoint with request validation
When I send invalid request data
Then the response status should be 400 Bad Request
  And the response should contain field-level errors
  And the response format should be standardized
  And errors should be logged with request context
```

### Scenario 2: Database Error Recovery
```gherkin
Given a temporary database connection failure
When an API request triggers database access
Then the error handler should attempt retry with backoff
  And if retry fails, return 503 Service Unavailable
  And include Retry-After header
  And log the error with full stack trace
```

### Scenario 3: Unhandled Exception Catching
```gherkin
Given an unexpected error occurs in endpoint code
When the exception bubbles up to the handler
Then the response status should be 500 Internal Server Error
  And the response should contain a correlation ID
  And sensitive information should be sanitized
  And full error details should be logged
```

## Technical Implementation Details

### Global Error Handler Middleware
```
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import traceback
import uuid

class ErrorHandlerMiddleware:
    async def __call__(self, request: Request, call_next):
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        try:
            response = await call_next(request)
            return response
            
        except ValidationError as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "validation_error",
                    "message": "Request validation failed",
                    "details": e.errors(),
                    "correlation_id": correlation_id
                }
            )
            
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": e.detail,
                    "correlation_id": correlation_id
                }
            )
            
        except DatabaseError as e:
            logger.error(f"Database error: {e}", extra={"correlation_id": correlation_id})
            return await handle_database_error(e, correlation_id)
            
        except Exception as e:
            logger.error(
                f"Unhandled exception: {e}",
                exc_info=True,
                extra={"correlation_id": correlation_id}
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "message": "An unexpected error occurred",
                    "correlation_id": correlation_id
                }
            )

async function handle_database_error(error: DatabaseError, correlation_id: str):
    if is_transient_error(error):
        return JSONResponse(
            status_code=503,
            content={
                "error": "service_unavailable",
                "message": "Database temporarily unavailable",
                "correlation_id": correlation_id,
                "retry_after": 30
            },
            headers={"Retry-After": "30"}
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "error": "database_error",
                "message": "Database operation failed",
                "correlation_id": correlation_id
            }
        )
```

## Definition of Done
- [ ] Global error handler middleware implemented
- [ ] All exceptions caught and handled
- [ ] Consistent error response format
- [ ] Correlation IDs for error tracking
- [ ] Sensitive data sanitization
- [ ] Comprehensive error logging
- [ ] Retry logic for transient failures
- [ ] Unit tests for all error types
- [ ] Integration tests pass
- [ ] Documentation updated